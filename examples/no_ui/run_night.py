import multiprocessing
from time import sleep
from datetime import datetime, time
from logging import INFO

from vnpy.event import EventEngine
from vnpy.trader.setting import SETTINGS
from vnpy.trader.engine import MainEngine

from vnpy_mc import McGateway
from vnpy_portfoliostrategy import PortfolioStrategyApp, StrategyEngine
from vnpy_portfoliostrategy.base import EVENT_PORTFOLIO_STRATEGY, EVENT_PORTFOLIO_LOG


SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True


ctp_setting = {
    "行情用户名": "207954",
    "行情密码": "!zzsr123456",
    "行情经纪商代码": "9999",
    "行情服务器": "180.168.146.187:10131",
    "交易用户名": "190018",
    "交易密码": "swhy1234",
    "交易经纪商代码": "2070",
    "交易服务器": "tcp://36.110.19.33:20669",
    "交易产品名称": "",
    "交易授权编码": "",
    "交易产品信息": "",
    "投机套利标志(1:投机/2:套利)": "1"
}


def pf(*args):
    print(f'[{datetime.now()}][PortfolioAuto] ',*args)


def run_child():
    """
    Running in the child process.
    """
    SETTINGS["log.file"] = True

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(McGateway)
    portfolio_engine = main_engine.add_app(PortfolioStrategyApp)
    main_engine.write_log("主引擎创建成功")

    log_engine = main_engine.get_engine("log")
    event_engine.register(EVENT_PORTFOLIO_LOG, log_engine.process_log_event)
    main_engine.write_log("注册日志事件监听")

    main_engine.connect(ctp_setting, "MC")
    main_engine.write_log("连接MC接口")

    sleep(60)

    portfolio_engine.init_engine()
    main_engine.write_log("PORTFOLIO引擎初始化完成")

    sleep(30)
    portfolio_engine.init_all_strategies()
    sleep(30)   # Leave enough time to complete strategy initialization
    main_engine.write_log("PORTFOLIO策略全部初始化")

    portfolio_engine.start_all_strategies()
    main_engine.write_log("PORTFOLIO策略全部启动")

    while True:
        sleep(1)


def run_parent():
    """
    Running in the parent process.
    """
    pf("启动PORTFOLIO策略守护父进程")

    # Chinese futures market trading period (day/night)
    DAY_START = time(8, 56)
    DAY_END = time(15, 30)

    NIGHT_START = time(20, 56)
    NIGHT_END = time(2, 45)

    child_process = None
    if (
            datetime.now().time() <= NIGHT_START or datetime.now().time() >= NIGHT_END
    ):
        pf("程序启动时，不在集合竞价时段，策略不运行")

    while True:

        current_time = datetime.now().time()
        trading = False

        # Check whether in trading period
        if (
            # (current_time >= DAY_START and current_time <= DAY_END)
            (current_time >= NIGHT_START)
            or (current_time <= NIGHT_END)
        ):
            trading = True

        # Start child process in trading period
        if trading and child_process is None:
            pf("启动子进程")
            child_process = multiprocessing.Process(target=run_child)
            child_process.start()
            pf("子进程启动成功")

        # 非记录时间则退出子进程
        if not trading and child_process is not None:
            pf("关闭子进程")
            child_process.terminate()
            child_process.join()
            child_process = None
            pf("子进程关闭成功")

        sleep(5)


if __name__ == "__main__":
    run_parent()
