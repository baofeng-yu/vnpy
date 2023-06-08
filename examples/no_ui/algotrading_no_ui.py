import csv
import os
import json
import multiprocessing
import psutil
import threading
import sys
from time import sleep

import uvicorn
from pymongo import daemon
from vnpy.trader.constant import Direction

from vnpy.trader.utility import get_folder_path

import vnpy.event
from datetime import datetime, time
from logging import INFO
from vnpy.trader.object import LogData
from typing import Any

from vnpy.event import EventEngine
from vnpy.trader.setting import SETTINGS
from vnpy.trader.engine import MainEngine, OmsEngine
from vnpy_algotrading import AlgoEngine
from vnpy_algotrading.base import EVENT_ALGO_LOG
from vnpy_algotrading import AlgoTradingApp

# from vnpy_ctp import CtpGateway

from fastapi import FastAPI, WebSocket
import asyncio
from vnpy_mc import McGateway

# load ctp settings from json file config.json
with open("C:\\Users\\swhysc\\Vnpy_Develop\\vnpy\\examples\\no_ui\\config.json", "r", encoding="utf-8") as f:
    config = json.load(f)
ctp_settings = config["ctp_settings"]
algo_settings_file = config["algo_settings_file"]
algo_logs_dir = config["algo_logs_dir"]

SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True
SETTINGS["log.file"] = True

# Chinese futures market trading period (day/night)
DAY_START = time(8, 45)
DAY_END = time(15, 30)

NIGHT_START = time(20, 45)
NIGHT_END = time(2, 45)


class AlgoTrader(threading.Thread):
    def __init__(self, algo_name: str, logs_queue: multiprocessing.Queue):
        super(AlgoTrader, self).__init__()
        # multi-process logs queue
        self.logs_queue = logs_queue
        # monitor part
        self.event = threading.Event()
        self.process_monitor: BackgroundMonitor
        # vnpy part
        self.event_engine: EventEngine
        self.main_engine: MainEngine
        self.oms_engine: OmsEngine
        self.algo_engine: AlgoEngine
        # algo part
        self.algo_settings_path: str
        self.algo_name: str = algo_name
        self.algo_setting: dict

    def _process_monitor_run(self):
        self.process_monitor = BackgroundMonitor(self.event, self.main_engine, self.logs_queue)
        self.process_monitor.start()
        return self.process_monitor.is_alive()

    def _initialize_vnpy(self):
        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)
        self.oms_engine = self.main_engine.get_engine("oms")
        self.main_engine.write_log("事件引擎创建成功")
        self.main_engine.write_log("主引擎创建成功")
        while not self.main_engine.add_gateway(McGateway):
            pass
        self.main_engine.write_log("添加Gateway成功")

        self.main_engine.add_app(AlgoTradingApp)
        self.main_engine.write_log("添加AlgoTradingApp")

        log_engine = self.main_engine.get_engine("log")
        self.event_engine.register(EVENT_ALGO_LOG, log_engine.process_log_event)
        self.event_engine.register(EVENT_ALGO_LOG, self.transfer_vnpy_logs2subprocess)
        self.main_engine.write_log("注册日志事件监听")

        # self.main_engine.connect(ctp_settings, "CTP")
        # self.main_engine.write_log("连接CTP接口")

        self.main_engine.connect(ctp_settings, "MC")
        self.main_engine.write_log("连接MC接口")

    def _initialize_algotrading(self):
        self.algo_settings_path = get_folder_path('.').joinpath("algo_settings", algo_settings_file)
        if not os.path.exists(self.algo_settings_path):
            self.main_engine.write_log(f"未在以下地址找到配置文件：{self.algo_settings_path}")
            self.main_engine.close()
            self.event.set()
            return False

        contracts = self.oms_engine.get_all_contracts()
        if contracts is None or len(contracts) == 0:
            self.main_engine.write_log("连接行情服务器失败，退出主引擎")
            self.main_engine.close()
            self.event.set()
            return False

        self.algo_engine: AlgoEngine = self.main_engine.get_engine("AlgoTrading")
        self.algo_engine.init_engine()
        return True

    def _algo_trader_run(self):
        """
            run all algos
        """
        # 当没有错误发生时启动算法
        # 合约行情订阅在算法内部初始化时执行
        for algo_template_setting in self.algo_settings:
            self.algo_engine.start_algo(self.algo_name, algo_template_setting["vt_symbol"],
                                        algo_template_setting["direction"], algo_template_setting["offset"],
                                        algo_template_setting["price"], algo_template_setting["volume"],
                                        algo_template_setting)

    def _load_settings_csv(self):
        """
            从csv文件载入algo配置，先订阅所有合约，再初始化算法
        """
        if not os.path.exists(self.algo_settings_path):
            if self.main_engine is not None:
                self.main_engine.write_log(f"algo配置文件{self.algo_settings_path}不存在")
            else:
                print(f"algo配置文件{self.algo_settings_path}不存在")
            return False

        # 创建csv DictReader
        with open(self.algo_settings_path, "r") as file:
            buf: list = [line for line in file.read().splitlines()]
            reader: csv.DictReader = csv.DictReader(buf)
        default_setting: dict = self.algo_engine.algo_templates[self.algo_name].default_setting
        # add additional setting to meet the requirements of vnpy3.7
        default_setting["vt_symbol"] = ""
        default_setting["direction"] = [Direction.LONG.value, Direction.SHORT.value]
        default_setting["volume"] = 0

        for field_name in iter(default_setting.keys()):
            if field_name not in reader.fieldnames:
                self.main_engine.write_log(f"CSV文件缺失算法{self.algo_name}所需字段{field_name}")
                return False

        settings: list = []

        for d in reader:
            # 用模版名初始化算法配置
            setting: dict = {
                "template_name": self.algo_name
            }

            # 读取csv文件每行中各个字段内容
            for field_name, tp in default_setting.items():
                field_type: Any = type(tp)
                field_text: str = d[field_name]

                if field_type == list:
                    field_value = field_text
                else:
                    try:
                        field_value = field_type(field_text)
                    except ValueError:
                        self.main_engine.write_log(f"{field_name}参数类型应为{field_type}，请检查!")
                        return False

                setting[field_name] = field_value

            setting["price"] = 100.0
            # 将setting添加到settings
            settings.append(setting)

        self.algo_settings = settings
        return True

    def transfer_vnpy_logs2subprocess(self, event: vnpy.event.Event):
        log: LogData = event.data
        self.logs_queue.put_nowait(log.msg)

    def run(self):
        self._initialize_vnpy()
        sleep(50)
        if not self._process_monitor_run():
            raise Exception("监控线程未正确启动，主程序退出")
        if not self._initialize_algotrading():
            raise Exception("算法引擎初始化失败，主程序退出")

        sleep(2)
        # todo 改为双向控制，monitor可以发信息给trader, 重新启动一次算法, 重新载入一次配置
        # todo 需要一个self.running?
        if self._load_settings_csv():
            self._algo_trader_run()
        else:
            self.logs_queue.put("异常")
            global log_generator
            log_generator.join()
            self.main_engine.write_log("初始化异常，算法停止，主引擎停止")
            self.main_engine.close()
            sleep(2)
            return

        print("如需停止主引擎，输入stop main\n如需停止算法交易，输入stop")

        while True:
            # if not self._check_trading_period():
            #     print("非交易时段，关闭AlgoTrading进程")
            #     self.main_engine.close()
            #     break
            if self.event.is_set():
                break
            sleep(10)

    def _check_trading_period(self):
        """"""
        current_time = datetime.now().time()
        trading = DAY_START <= current_time <= DAY_END or current_time >= NIGHT_START or current_time <= NIGHT_END
        return trading


class BackgroundMonitor(threading.Thread):
    def __init__(self, event: threading.Event, main_engine: MainEngine, logs_queue: multiprocessing.Queue):
        super(BackgroundMonitor, self).__init__(daemon=True)
        self.event: threading.Event = event
        self.main_engine = main_engine
        self.aligo_engine: AlgoEngine = self.main_engine.get_engine('AlgoTrading')
        self.logs_queue = logs_queue

    async def __get_command(self):
        return sys.stdin.readline().rstrip('\n')

    def __stop_vnpy(self):
        self.event.set()
        self.logs_queue.put("stop")
        self.main_engine.write_log("主引擎关闭")
        self.aligo_engine.stop_all()
        self.main_engine.close()

    def __stop_algo_engine(self):
        self.main_engine.write_log("停止一篮子算法")
        self.aligo_engine.stop_all()

    def run(self):
        while not self.event.is_set():
            try:
                command = asyncio.run(self.__get_command())
                if command == "stop main":
                    self.__stop_vnpy()
                    break

                if command == "stop":
                    self.__stop_algo_engine()

            except UnicodeDecodeError:
                self.__stop_vnpy()
                break


class LogGenerator(multiprocessing.Process):
    def __init__(self, algo_name: str, logs_queue: multiprocessing.Queue):
        super(LogGenerator, self).__init__(daemon=True)
        self.logs_queue: multiprocessing.Queue = logs_queue
        self.algo_name = algo_name

    def run(self):
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 启动日志记录子进程")
        if not os.path.exists(algo_logs_dir):
            os.mkdir(algo_logs_dir)

        with open(os.path.join(algo_logs_dir, f'{self.algo_name}.log'), 'w') as log_file:
            while True:
                try:
                    log: str = self.logs_queue.get_nowait()
                    log_file.write(log + '\n')
                    if log == 'stop':
                        break
                except Exception as e:
                    pass

        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 主引擎终止，日志记录进程同步中止")


class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_message(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


app = FastAPI()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    manager = ConnectionManager()
    await manager.connect(websocket)
    try:
        while True:
            await manager.send_message("Hello World")
            await asyncio.sleep(1)
    except Exception as e:
        print(e)
    finally:
        manager.disconnect(websocket)


if __name__ == "__main__":
    logs = multiprocessing.Queue()
    log_generator = LogGenerator("FeedbackTWAP", logs)
    log_generator.start()
    print("log_generator pid: %d" % log_generator.pid)
    psutil.Process(pid=log_generator.pid).cpu_affinity([7, 8])
    # start algo-trading in the main process
    algo_trader = AlgoTrader("FeedbackTWAP", logs)
    algo_trader.start()
    psutil.Process(pid=os.getpid()).cpu_affinity([2, 3])
    print("main process pid: %d" % os.getpid())
    # start logging subprocess
    uvicorn.run("algotrading_no_ui:app", host="localhost", port=8000, reload=True, workers=3)

    log_generator.terminate()
    log_generator.join()
    log_generator.close()
    exit(0)
