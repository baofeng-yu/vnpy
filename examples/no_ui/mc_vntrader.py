import typing
from logging import INFO
from vnpy.event import EventEngine
from vnpy.trader.engine import LogEngine, MainEngine
from vnpy.trader.setting import SETTINGS
from vnpy.trader.ui import MainWindow, create_qapp
from vnpy_algotrading import AlgoTradingApp
from vnpy_algotrading.base import EVENT_ALGO_LOG
from vnpy_mc import McGateway
from vnpy_portfoliostrategy import PortfolioStrategyApp
from vnpy_riskmanager import RiskManagerApp

SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True
SETTINGS["log.file"] = True


def main():
    """主入口函数"""
    qapp = create_qapp()

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    log_engine: LogEngine = typing.cast(LogEngine, main_engine.get_engine("log"))
    event_engine.register(EVENT_ALGO_LOG, log_engine.process_log_event)
    main_engine.add_gateway(McGateway)
    main_engine.add_app(AlgoTradingApp)
    main_engine.add_app(PortfolioStrategyApp)
    main_engine.add_app(RiskManagerApp)
    main_engine.write_log("初始化完成")

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec()


if __name__ == "__main__":
    main()
