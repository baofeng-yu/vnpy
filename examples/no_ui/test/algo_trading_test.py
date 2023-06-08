import datetime
import typing
from logging import INFO

from PySide6 import QtWidgets
from PySide6.QtCore import QTimer
from vnpy_algotrading.ui.widget import AlgoWidget

from vnpy.event import EventEngine
from vnpy.trader.engine import LogEngine, MainEngine
from vnpy.trader.setting import SETTINGS
from vnpy.trader.ui import MainWindow, create_qapp
from vnpy_algotrading import AlgoTradingApp
from vnpy_algotrading.base import EVENT_ALGO_LOG
from vnpy_mc import McGateway

SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True
SETTINGS["log.file"] = True
vt_symbol = "TF2309"
volume = 5
SETTINGS["log.filename"] = f"{vt_symbol}_{volume}_single_成交_等待_拒单_风控"

DAY_START = datetime.time(8, 45)
DAY_END = datetime.time(15, 30)

ctp_settings = {
    "行情用户名": "207954",
    "行情密码": "!zzsr123456",
    "行情经纪商代码": "9999",
    "行情服务器": "180.168.146.187:10211" if DAY_START < datetime.datetime.now().time() < DAY_END
    else "180.168.146.187:10131",
    "交易用户名": "190018",
    "交易密码": "swhy1234",
    "交易经纪商代码": "2070",
    "交易服务器": "tcp://36.110.19.33:20669",
    "交易产品名称": "",
    "交易授权编码": "",
    "交易产品信息": "",
    "投机套利标志(1:投机/2:套利)": "1"
}


def main():
    """主入口函数"""
    qapp = create_qapp()

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    log_engine: LogEngine = typing.cast(LogEngine, main_engine.get_engine("log"))
    event_engine.register(EVENT_ALGO_LOG, log_engine.process_log_event)
    main_engine.add_gateway(McGateway)
    main_engine.add_app(AlgoTradingApp)
    main_engine.write_log("初始化完成")

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    main_window.connect("MC", show_widget=False)
    # unit is milliseconds, all commands-clock start at the same beginning point
    QTimer.singleShot(1000, main_window.dialog.button.click)

    for app_name, widget in main_window.widgets_classes.items():
        if app_name == "AlgoTrading":
            main_window.initiate_algo_widget(widget, app_name)

    form_params: dict = {
        "vt_symbol": "TF2309.CFFEX",
        "direction": "空",
        "offset": "开",
        "price": 0.0,
        "volume": 10,
        "time": 60,
        "interval": 5,
        "schedual_uplimit_offset": 5,
        "schedual_lowlimit_offset": 5,
    }
    combox_parameters = {
        "direction": {"空": 0, "开": 1, "": 0},
        "offset": {"开": 0, "平": 1, "平今": 2, "平昨": 3, "": 0},
    }

    if main_window.algo_widget:
        print("starting algo")
        for algo_widget in main_window.algo_widget.algo_widgets:
            if algo_widget == "FeedbackTWAP":
                real_algo_widget = main_window.algo_widget.algo_widgets[algo_widget]
                for form_widget_name, (form_widget, data_type) in real_algo_widget.widgets.items():
                    if isinstance(form_widget, QtWidgets.QComboBox):
                        form_widget.setCurrentIndex(combox_parameters[form_widget_name][form_params.get(form_widget_name, "")])
                    else:
                        form_widget.setText(str(form_params.get(form_widget_name, "")))

    main_window.open_algo_widget()

    qapp.exec()


if __name__ == "__main__":
    main()
