# -*- coding: utf-8 -*-

"""
生产环境使用时请注释掉第51行mcctp_setting = test_mcctp_setting
本脚本限制了运行时间为夜盘开盘集合竞价时间段,如果完全信任任务调度计划,可注释掉run方法
if not valid_night_start_time():一段检查处理
"""
from time import sleep
from datetime import datetime, time
from logging import INFO
from typing import cast

from vnpy.event import EventEngine, Event
from vnpy.trader.setting import SETTINGS
from vnpy.trader.engine import MainEngine, LogEngine
from vnpy_mc import McGateway
from vnpy_portfoliostrategy import PortfolioStrategyApp, StrategyEngine
from vnpy_portfoliostrategy.base import EVENT_PORTFOLIO_STRATEGY, EVENT_PORTFOLIO_LOG

SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True
SETTINGS["log.file"] = True

DAY_START = time(8, 55)
DAY_AUCTION_END = time(9, 00)
DAY_END = time(15, 30)

NIGHT_START = time(20, 55)
NIGHT_AUCTION_END = time(21, 00)
NIGHT_END = time(2, 45)

#生产环境
mcctp_setting = {
    "行情用户名": "901000",
    "行情密码": "",
    "行情经纪商代码": "88888",
    "行情服务器": "172.17.48.113:31213",
    "交易用户名": "190004",
    "交易密码": "swhy1234",
    "交易经纪商代码": "7090",
    "交易服务器": "172.17.196.183:20669",
    "交易产品名称": "",
    "交易授权编码": "",
    "交易产品信息": "",
    "投机套利标志(1:投机/2:套利)": "1"
}
#测试环境
test_mcctp_setting = {
    "行情用户名": "207954",
    "行情密码": "!zzsr123456",
    "行情经纪商代码": "9999",
    "行情服务器": "180.168.146.187:10211" if DAY_START < datetime.now().time() < DAY_END else "180.168.146.187:10131",
    "交易用户名": "190018",
    "交易密码": "swhy1234",
    "交易经纪商代码": "2070",
    "交易服务器": "tcp://36.110.19.33:20669",
    "交易产品名称": "",
    "交易授权编码": "",
    "交易产品信息": "",
    "投机套利标志(1:投机/2:套利)": "1"
}

mcctp_setting = test_mcctp_setting


def pf(*args):
    print(f'[{datetime.now()}] ', *args)


strategies_tracker = dict()


def valid_night_start_time():
    current_time = datetime.now().time()
    if not (NIGHT_START < current_time < NIGHT_AUCTION_END): 
        return False
    return True


def valid_day_start_time():
    current_time = datetime.now().time()
    if not (DAY_START < current_time < DAY_AUCTION_END): 
        return False
    return True


def process_strategy_event(event: Event):
    global strategies_tracker
    if event.type == EVENT_PORTFOLIO_STRATEGY:
        strategy_state = event.data
        strategy_name = strategy_state["strategy_name"]
        strategy_inited = strategy_state["inited"]
        strategy_trading = strategy_state["trading"]
        # strategy_tracker[...] = [strategy,inited, strategy.trading, has_started_flag]

        if strategy_name in strategies_tracker and strategies_tracker[strategy_name] == [True, False, False] and strategy_trading:
            strategies_tracker[strategy_name] = [strategy_inited, strategy_trading, True]
        elif strategy_name in strategies_tracker:
            strategies_tracker[strategy_name][:2] = [strategy_inited, strategy_trading]
        else:
            strategies_tracker[strategy_name] = [strategy_inited, strategy_trading, False]

def run():
    #
    # if not valid_night_start_time():
    #     pf("当前时间不在夜盘集合竞价时间范围内，程序不予执行")
    #     input("输入任意键可退出")
    #     return
    #
    # if not valid_day_start_time():
    #     pf("当前时间不在日盘集合竞价时间范围内，程序不予执行")
    #     input("输入任意键可退出")
    #     return

    # 事件引擎的定时器触发区间，默认1s一次
    event_engine = EventEngine(interval=1)
    event_engine.register(EVENT_PORTFOLIO_STRATEGY, process_strategy_event)
    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(McGateway)
    main_engine.add_app(PortfolioStrategyApp)

    portfolio_engine: StrategyEngine = cast(StrategyEngine, main_engine.get_engine("PortfolioStrategy"))
    main_engine.write_log("主引擎创建成功")

    log_engine: LogEngine = cast(LogEngine, main_engine.get_engine("log"))
    event_engine.register(EVENT_PORTFOLIO_LOG, log_engine.process_log_event)
    main_engine.write_log("注册日志事件监听")

    main_engine.connect(mcctp_setting, "MC")
    main_engine.write_log("连接MC接口")

    sleep(50)
    portfolio_engine.init_engine()
    main_engine.write_log("PORTFOLIO引擎初始化完成")
    portfolio_engine.init_all_strategies()
    sleep(15)
    main_engine.write_log("PORTFOLIO策略全部初始化")

    portfolio_engine.start_all_strategies()
    main_engine.write_log("PORTFOLIO策略全部启动")
    sleep(15)

    # while True:
    #     current_time = datetime.now().time()
    #     if NIGHT_END < current_time < DAY_START or DAY_END < current_time < NIGHT_START:
    #         main_engine.write_log(f"当前时间[{current_time}]已过交易时间，PORTFOLIO策略退出")
    #         break
    #     else:
    #         sleep(10)
    global strategies_tracker
    while True:
        # 有策略曾经被启动并被记录，且所有策略都是inited=True，trading=False，started_flag = True的状态
        # 则认为所有策略都已运行结束，此时可以退出主引擎，保险起见，此时要再次调用stop_all_strategies()
        if len(strategies_tracker) != 0 and all(strategy[0] and not strategy[1] and strategy[2] for strategy in strategies_tracker.values()):
            break
        sleep(15)

    portfolio_engine.stop_all_strategies()
    main_engine.close()
    sleep(5)

    input("主引擎已关闭,输入任意键可退出: ")


if __name__ == "__main__":
    run()
