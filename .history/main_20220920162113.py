
import sys
import os
import threading
import time
os.environ['PYTHON_VLC_MODULE_PATH'] = "./vlc"
import logging
import vlc
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtWebEngineWidgets import *
from PyQt5.QtPrintSupport import *
from chitu import Ui_MainWindow
from AGV import agv
from UVC_Controller import UVCController


CameraSetting = {
    'AbsolutePanMin'        : -170, 
    'AbsolutePanMax'        : 170, 
    'AbsoluteTiltMin'       : -30, 
    'AbsoluteTiltMax'       : 90, 
    'AbsoluteZoomMin'       : 1, 
    'AbsoluteZoomMax'       : 16384
}

class vlc_player():
    def __init__(self):
        self.Instance = vlc.Instance(['--video-on-top'])
        self.player = self.Instance.media_player_new()
        self.player.video_set_mouse_input(False)
        self.player.video_set_key_input(False)
        self.player.set_mrl("rtsp://admin:admin@192.168.8.251:554/live/av0", "network-caching=300")
        self.player.audio_set_mute(True)
    
class MainWindow(QMainWindow, Ui_MainWindow):

    def __init__(self, parent=None):
        
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)
        self.translate = QCoreApplication.translate
        self.speed = 0.0
        self.x = 0
        self.y = 0
        self.angle = 0
        self.VisualStatusVal_to_Word_Dict = {
            -1  : 'Close', 
            0   : 'Uninit', 
            1   : 'Tracking', 
            2   : 'Lost'
        }
        try:
            self.agv = agv()
            self.SET_robot_info_to_app()
            self.control_event = threading.Event()
            self.shutdown_event = threading.Event()
            self.control_thread = threading.Thread(target=self.AGV_control_thread, args=[0.5])
            self.control_thread.start()
        except:
            logging.warning('not connected')
            self.agv = 0
        
        self.SET_mouse_event_to_control_robot_AGV_button()
        self.SpeedSlider.valueChanged.connect(self.SET_speed_slider_to_local_speed)
        
        self.camera = UVCController(0x04B4, 0x00F9)
        self.SET_Camera_Slider()
        self.connect_slider_spinBox()
        self.camera.PanTiltAbsoluteControl(0, 0)
        self.camera.ZoomAbsoluteControl(0)
        
        self.videoPlayer = vlc_player().player
        # self.frame.mouseDoubleClickEvent = self.mouse_event
        if sys.platform.startswith('linux'): # for Linux using the X Server
            self.videoPlayer.set_xwindow(self.video_widget.winId())
        elif sys.platform == "win32": # for Windows
            self.videoPlayer.set_hwnd(self.video_widget.winId())
        elif sys.platform == "darwin": # for MacOS
            self.videoPlayer.set_nsobject(int(self.video_widget.winId()))
        self.videoPlayer.play()

        self.show()
    def closeEvent (self, event):
        self.shutdown_event.set()
        self.control_thread.join()
    def SET_robot_info_to_app(self):
        res = self.agv.GET_robot_info()
        
        # if not res['charge']:
        #     self.BatteryLevelVal.setText(self.translate("MainWindow", str(res['battery'])+'%'+' Plugged in'))
        # else:
        #     self.BatteryLevelVal.setText(self.translate("MainWindow", str(res['battery'])+'%'+' On Battery'))
        self.BatteryLevelVal.setText(self.translate("MainWindow", str(res['battery'])+'%'))
        
        self.RobotVersionVal.setText(self.translate("MainWindow", str(res['info']['version'])))
        res = self.agv.GET_galileo_status()
        
        self.VisualStatusVal.setText(self.translate("MainWindow", self.VisualStatusVal_to_Word_Dict[res['visualStatus']]))
        
        if res['busyStatus']:
            self.ProcessingStatusVal.setText(self.translate("MainWindow", 'Busy'))
        else:
            self.ProcessingStatusVal.setText(self.translate("MainWindow", 'Running'))
        self.VoltageVal.setText(self.translate("MainWindow", str(round(res['power'], 2))+' V'))

# Camera Control
   
    def SET_Camera_Slider(self):
        self.PanSlider.setMinimum(CameraSetting['AbsolutePanMin'])
        self.PanspinBox.setMinimum(CameraSetting['AbsolutePanMin'])
        self.PanSlider.setMaximum(CameraSetting['AbsolutePanMax'])
        self.PanspinBox.setMaximum(CameraSetting['AbsolutePanMax'])
        self.TiltSlider.setMinimum(CameraSetting['AbsoluteTiltMin'])
        self.TiltspinBox.setMinimum(CameraSetting['AbsoluteTiltMin'])
        self.TiltSlider.setMaximum(CameraSetting['AbsoluteTiltMax'])
        self.TiltspinBox.setMaximum(CameraSetting['AbsoluteTiltMax'])
        self.ZoomSlider.setMinimum(CameraSetting['AbsoluteZoomMin'])
        self.ZoomspinBox.setMinimum(CameraSetting['AbsoluteZoomMin'])
        self.ZoomSlider.setMaximum(CameraSetting['AbsoluteZoomMax'])
        self.ZoomspinBox.setMaximum(CameraSetting['AbsoluteZoomMax'])
        self.PanSlider.setSingleStep(1)
        self.TiltSlider.setSingleStep(1)
        self.ZoomSlider.setSingleStep(1)
        self.PanspinBox.setSingleStep(1)
        self.TiltspinBox.setSingleStep(1)
        self.ZoomspinBox.setSingleStep(1)
        self.PanSlider.setValue(0)
        self.TiltSlider.setValue(0)
        
    def connect_slider_spinBox(self):
        self.PanSlider.valueChanged.connect(lambda:self._change_value(self.PanspinBox, self.PanSlider.value(), 'Pan'))
        self.TiltSlider.valueChanged.connect(lambda:self._change_value(self.TiltspinBox, self.TiltSlider.value(), 'Tilt'))
        self.ZoomSlider.valueChanged.connect(lambda:self._change_value(self.ZoomspinBox, self.ZoomSlider.value(), 'Zoom'))
        self.PanspinBox.valueChanged.connect(lambda:self._change_value(self.PanSlider, self.PanspinBox.value(), 'Pan'))
        self.TiltspinBox.valueChanged.connect(lambda:self._change_value(self.TiltSlider, self.TiltspinBox.value(), 'Tilt'))
        self.ZoomspinBox.valueChanged.connect(lambda:self._change_value(self.ZoomSlider, self.ZoomspinBox.value(), 'Zoom'))
    
    def _change_value(self, var, val, name):
        var.setValue(val)
        if name == 'Pan' or name == 'Tilt':
            self.camera.PanTiltAbsoluteControl(self.PanSlider.value(), self.TiltSlider.value())
        elif name == 'Zoom':
            self.camera.ZoomAbsoluteControl(self.ZoomSlider.value())
# End of Camera Control

    def SET_mouse_event_to_control_robot_AGV_button(self):
        self.up.pressed.connect(lambda: self.AGV_control_pressed_event('up'))
        self.up.released.connect(lambda: self.AGV_control_released_event('up'))

    def SET_speed_slider_to_local_speed(self, val):
        self.speed = val/100.0
        self.SpeedVal.setText(self.translate("MainWindow", str(self.speed)))
        
    def AGV_control_pressed_event(self, dir=None):
        if dir == 'up':
            self.x = 1.0
        elif dir == 'down':
            self.x = -1.0
        elif dir == 'left':
            self.angle = 1.0
        elif dir == 'right':
            self.angle = -1.0
        if self.agv:
            self.control_event.set()
            # self.agv.PUT_robot_speed(x = self.x * self.speed, angle = self.angle * self.speed)
        # logging.debug('speed_x: {}, speed_angle: {}, speed_factor: {}'.format(self.x, self.angle, self.speed))
        
    def AGV_control_released_event(self, dir=None):
        if dir == 'up' or dir == 'down':
            self.x = 0.0
        elif dir == 'left' or dir == 'right':
            self.angle = 0.0
        if self.agv:
            self.control_event.set()
            # self.agv.PUT_robot_speed(x = self.x * self.speed, angle = self.angle * self.speed)
        # logging.debug('speed_x: {}, speed_angle: {}, speed_factor: {}'.format(self.x, self.angle, self.speed))

    def AGV_control_thread(self, timeout):
        while not self.shutdown_event.is_set():
            
            self.control_event.wait(timeout)
            self.agv.PUT_robot_speed(x = self.x * self.speed, angle = self.angle * self.speed)
            self.control_event.clear()
            logging.debug('speed_x: {}, speed_angle: {}, speed_factor: {}'.format(self.x, self.angle, self.speed))
            
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_W and self.x != 1.0:
            self.AGV_control_pressed_event(dir='up')
        elif event.key() == Qt.Key_S and self.x != -1.0:
            self.AGV_control_pressed_event(dir='down')
        elif event.key() == Qt.Key_A and self.angle != 1.0:
            self.AGV_control_pressed_event(dir='left')            
        elif event.key() == Qt.Key_D and self.angle != -1.0:
            self.AGV_control_pressed_event(dir='right')
            
    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_W and not event.isAutoRepeat():
            self.AGV_control_released_event(dir='up')
        elif event.key() == Qt.Key_S and not event.isAutoRepeat():
            self.AGV_control_released_event(dir='down')
        elif event.key() == Qt.Key_A and not event.isAutoRepeat():
            self.AGV_control_released_event(dir='left')            
        elif event.key() == Qt.Key_D and not event.isAutoRepeat():
            self.AGV_control_released_event(dir='right')
            
    # def mousePressEvent(self, event):
    #     print('in')
    #     if event.button() == Qt.LeftButton:
    #         if (event.x() >= self.up.x() and event.x() <= self.up.x() + self.up.width())\
    #             and (event.y() >= self.up.y() and event.y() <= self.up.y() + self.up.height()):
    #             print('pressed')
    
    # def mouseDoubleClickEvent(self, event):
    #     print('trigger mouseDoubleClickEvent')
    #     if event.button() == Qt.LeftButton:
    #         if self.windowState() == Qt.WindowNoState:
    #             # self.videoFrame1.hide()
    #             # self.frame.show()
    #             print('fullscreen')
                
    #             # self.setWindowState(self.windowState() ^  Qt.WindowFullScreen)
    #             # self.video_widget.setfullscreen()
    #             # self.video_widget.setWindowState(self.video_widget.windowState() ^ Qt.WindowFullScreen)
    #         else:
    #             # self.videoFrame1.show()
    #             print('not fullscreen')
    #             self.video_widget.setWindowState(Qt.WindowNoState)
    #             self.setWindowState(Qt.WindowNoState)
    def __del__(self):
        self.window.control_thread.join()
class Application():
    def __init__(self):
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(module)s - %(funcName)s]: %(message)s", handlers=[logging.StreamHandler(), logging.FileHandler('debug.log')] )
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("simulator")
        self.window = MainWindow()
        self.app.exec_()
        self.window.control_thread.join()


    

if __name__ == "__main__":
    app = Application()
    
    