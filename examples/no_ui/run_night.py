from time import sleep
from datetime import datetime
from logging import INFO
from typing import cast

from vnpy.event import EventEngine
from vnpy.trader.setting import SETTINGS
from vnpy.trader.engine import MainEngine, LogEngine
from vnpy_mc import McGateway

from vnpy_portfoliostrategy import PortfolioStrategyApp, StrategyEngine
from vnpy_portfoliostrategy.base import EVENT_PORTFOLIO_LOG

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


def pf(*args):
    print(f'[{datetime.now()}][PortfolioAuto] ',*args)


def main():
    """
    Running in the child process.
    """
    event_engine: EventEngine = EventEngine()
    main_engine: MainEngine = MainEngine(event_engine)
    main_engine.add_gateway(McGateway)
    main_engine.add_app(PortfolioStrategyApp)
    portfolio_engine: StrategyEngine = cast(StrategyEngine, main_engine.get_engine("PortfolioStrategy"))
    main_engine.write_log("主引擎创建成功")

    log_engine: LogEngine = cast(LogEngine, main_engine.get_engine("log"))
    event_engine.register(EVENT_PORTFOLIO_LOG, log_engine.process_log_event)
    main_engine.write_log("注册日志事件监听")
    main_engine.connect(ctp_setting, "MCTEST")
    main_engine.write_log("连接Mc-Test接口")
    # main_engine.connect(ctp_setting, "MC2")
    # main_engine.write_log("连接MC2接口")
    sleep(30)
    portfolio_engine.init_engine()
    main_engine.write_log("PORTFOLIO引擎初始化完成")

    sleep(30)
    portfolio_engine.init_all_strategies()
    sleep(30)   # Leave enough time to complete strategy initialization
    main_engine.write_log("PORTFOLIO策略全部初始化")

    # portfolio_engine.start_all_strategies()
    main_engine.write_log("PORTFOLIO策略全部启动")

    input("输入任意内容停止进程：")
    portfolio_engine.stop_all_strategies()
    main_engine.write_log("PORTFOLIO策略全部停止")
    main_engine.close()
    print("主引擎停止")


if __name__ == "__main__":
    main()
