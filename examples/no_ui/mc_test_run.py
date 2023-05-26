import sys
import time
import csv
import json
import os
import typing
from logging import INFO
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine, LogEngine
from vnpy.trader.setting import SETTINGS
from vnpy.trader.utility import get_folder_path
from vnpy_algotrading import AlgoTradingApp, AlgoEngine
from vnpy_algotrading.base import EVENT_ALGO_LOG
from vnpy_mc import McGateway  # type: ignore

SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True
SETTINGS["log.file"] = True

ctp_setting = {
    "行情用户名": "207954",
    "行情密码": "!zzsr123456",
    "行情经纪商代码": "9999",
    "行情服务器": "180.168.146.187:10211",
    "交易用户名": "190018",
    "交易密码": "swhy1234",
    "交易经纪商代码": "2070",
    "交易服务器": "tcp://36.110.19.33:20669",
    "交易产品名称": "",
    "交易授权编码": "",
    "交易产品信息": "",
    "投机套利标志(1:投机/2:套利)": "1"
}
algo_settings_path = get_folder_path('.').joinpath("algo_settings", "feedback_twap_contracts.csv")


def _load_settings_csv(main_engine: MainEngine, algo_name):
    """
        从csv文件载入algo配置，先订阅所有合约，再初始化算法
    """
    if not os.path.exists(algo_settings_path):
        if main_engine is not None:
            main_engine.write_log(f"algo配置文件{algo_settings_path}不存在")
        else:
            print(f"algo配置文件{algo_settings_path}不存在")
        return []

    # 创建csv DictReader
    with open(algo_settings_path, "r") as file:
        buf: list = [line for line in file.read().splitlines()]
        reader: csv.DictReader = csv.DictReader(buf)
    algo_engine: AlgoEngine = typing.cast(AlgoEngine, main_engine.get_engine("AlgoTrading"))
    default_setting: dict = algo_engine.algo_templates[algo_name].default_setting
    for field_name in iter(default_setting.keys()):
        if field_name not in reader.fieldnames:
            main_engine.write_log(f"CSV文件缺失算法{algo_name}所需字段{field_name}")
            return []

    algo_settings: list = []

    for d in reader:
        # 用模版名初始化算法配置
        setting: dict = {
            "template_name": algo_name
        }

        # 读取csv文件每行中各个字段内容
        for field_name, tp in iter(default_setting.items()):
            field_type: typing.Any = type(tp)
            field_text: str = d[field_name]

            if field_type == list:
                field_value = field_text
            else:
                try:
                    field_value = field_type(field_text)
                except ValueError:
                    main_engine.write_log(f"{field_name}参数类型应为{field_type}，请检查!")
                    return []

            setting[field_name] = field_value
        setting["algo_name"] = algo_name
        setting["price"] = 100.0
        # 将setting添加到settings
        algo_settings.append(setting)

    return algo_settings


def main():
    """主入口函数"""
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    log_engine: LogEngine = typing.cast(LogEngine, main_engine.get_engine("log"))
    event_engine.register(EVENT_ALGO_LOG, log_engine.process_log_event)

    main_engine.add_gateway(McGateway)
    main_engine.add_app(AlgoTradingApp)
    main_engine.connect(ctp_setting, "MC")
    main_engine.write_log("初始化完成")
    time.sleep(60)

    algo_engine: AlgoEngine = typing.cast(AlgoEngine, main_engine.get_engine("AlgoTrading"))
    main_engine.write_log("初始化算法交易引擎")
    algo_template_settings = _load_settings_csv(main_engine, "FeedbackTWAPAlgo")
    algo_engine.init_engine()
    for algo_template_setting in algo_template_settings:
        active_algo_name = algo_engine.start_algo(algo_template_setting["algo_name"], algo_template_setting["vt_symbol"], algo_template_setting["direction"], algo_template_setting["offset"], algo_template_setting["price"], algo_template_setting["volume"], algo_template_setting)

    main_engine.write_log("输入任意键可终止算法引擎")
    algo_engine.stop_all()
    main_engine.write_log("所有算法已停止")
    main_engine.close()
    print("主引擎已停止")
    sys.exit(0)


if __name__ == "__main__":
    main()