
import sys
import os
import threading
import time
os.environ['PYTHON_VLC_MODULE_PATH'] = "./vlc"
import logging
import logging.config
import vlc
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtWebEngineWidgets import *
from PyQt5.QtPrintSupport import *

from chitu import Ui_MainWindow
from AGV import agv
from AGV_MAP_UTIL import *
from UVC_Controller import UVCController
from ptz_control import *

from datetime import datetime

import yaml
with open("logger_setting.yaml","r") as f:
    config = yaml.full_load(f)
    logger = logging.config.dictConfig(config)

CAMERA_VID = 0x04B4
Camera_PID = 0x00F9
# can be searched by ws dircovery
#not implemented yet
CameraIP = '192.168.8.251'
CameraSetting = {
    'AbsolutePanMin'        : -170, 
    'AbsolutePanMax'        : 170, 
    'AbsoluteTiltMin'       : -30, 
    'AbsoluteTiltMax'       : 90, 
    'AbsoluteZoomMin'       : 1, 
    'AbsoluteZoomMax'       : 16384
}

class vlc_player():
    def __init__(self, url):
        self.Instance = vlc.Instance() # ['--video-on-top']
        self.player = self.Instance.media_player_new()
        self.player.video_set_mouse_input(False)
        self.player.video_set_key_input(False)
        self.player.set_mrl(url, "network-caching=1000")
        self.player.audio_set_mute(True)
    
class MainWindow(QMainWindow, Ui_MainWindow):

    def __init__(self, parent=None):
        
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)
        logging.info("Initialize main window")
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
            self.control_event = threading.Event()
            self.shutdown_event = threading.Event()
            
            self.periodic_info_thread = threading.Thread(target=self.AGV_info_thread, args=[5])
            self.control_thread = threading.Thread(target=self.AGV_control_thread, args=[0.5])
            
            self.periodic_info_thread.start()
            self.control_thread.start()
            
            # get map
            self.agv.GET_start_navigation()
            result = self.agv.GET_current_map()
            map = result['name']
            Qmap = QPixmap()
            Qmap.loadFromData(self.agv.GET_map_png(map), 'png')
            self.AGV_MAP_IMG.setPixmap(Qmap)
            self.agv.GET_stop_navigation()
            ###############################
            # Navigation settings
            self.nav_task_stat = False
            self.maps = from_json_to_map(self.agv.GET_navigation_points_connections())
            self.MAP.addItems(list(self.maps.keys()))
            self.PATH.addItems(list(self.maps[self.MAP.currentText()].paths.keys()))
            ls = list(self.maps[self.MAP.currentText()].paths[self.PATH.currentText()].points.keys())
            ls.insert(0, 'auto')
            self.Point.addItems(ls)
            self.MAP.currentIndexChanged.connect(self.map_combobox_change_path_box)
            self.PATH.currentIndexChanged.connect(self.path_combobox_change_point_box)

            self.Start_Navigation.clicked.connect(self.start_close_navigation)
            self.start_navigate_pt_button.clicked.connect(self.start_pause_navigation)
            self.Navigation_Cancel.clicked.connect(self.stop_navigation)
            
            
        except:
            logging.error('not connected')
            self.agv = 0

        self.SET_mouse_event_to_control_robot_AGV_button()
        self.SpeedSlider.valueChanged.connect(self.SET_speed_slider_to_local_speed)
        
        self.tabWidget.setCurrentIndex(0)
        self.SET_Camera_Slider()
        try:
            self.camera = UVCController(CAMERA_VID, CAMERA_PID)
        except:
            try:
                self.camera = ptzControl(CameraIP, 80, 'admin', 'password')
                def PanTiltAbsoluteControl(x, y):
                    self.camera.move_abspantilt(x, y, 1)
                def ZoomAbsoluteControl(speed):
                    self.zoom(speed)
                # current zoom not in absolute control
            except:
                self.camera = 0
        if self.camera:
            self.connect_slider_spinBox()
            self.camera.PanTiltAbsoluteControl(0, 0)
            self.camera.ZoomAbsoluteControl(0)
        
        self.videoPlayer = vlc_player("rtsp://admin:password@{}:554/live/av0".format(CameraIP)).player
        if self.agv:
            # get bottom camera image
            self.bottom_camera = vlc_player("http://{ip}:8080/stream?topic=/camera_node/image_raw".format(ip=self.agv.robot_ip)).player
        
        # self.frame.mouseDoubleClickEvent = self.mouse_event
        if sys.platform.startswith('linux'): # for Linux using the X Server
            self.videoPlayer.set_xwindow(self.video_widget.winId())
            self.bottom_camera.set_xwindow(self.AGV_CAMERA_VID.winId())
        elif sys.platform == "win32": # for Windows
            self.videoPlayer.set_hwnd(self.video_widget.winId())
            self.bottom_camera.set_hwnd(self.AGV_CAMERA_VID.winId())
        elif sys.platform == "darwin": # for MacOS
            self.videoPlayer.set_nsobject(int(self.video_widget.winId()))
            self.bottom_camera.set_nsobject(int(self.AGV_CAMERA_VID.winId()))
        self.videoPlayer.play()
        self.bottom_camera.play()

        self.Navigation_Cancel.hide()
        self.Target_Navigation_Widget.hide()
        
        self.setWindowState(Qt.WindowMaximized)
        self.show()
        
    def closeEvent (self, event):
        self.speed = 0.0
        self.control_event.set()
        self.shutdown_event.set()
        self.periodic_info_thread.join()
        self.control_thread.join()
        if self.agv:
            self.agv.GET_stop_navigation()
        
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
        self.VoltageVal.setText(self.translate("MainWindow", str(round(res['power'], 1))+' V'))

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
# AGV speed control
    def SET_mouse_event_to_control_robot_AGV_button(self):
        self.up.pressed.connect(lambda: self.AGV_control_pressed_event('up'))
        self.up.released.connect(lambda: self.AGV_control_released_event('up'))
        self.down.pressed.connect(lambda: self.AGV_control_pressed_event('down'))
        self.down.released.connect(lambda: self.AGV_control_released_event('down'))
        self.left.pressed.connect(lambda: self.AGV_control_pressed_event('left'))
        self.left.released.connect(lambda: self.AGV_control_released_event('left'))
        self.right.pressed.connect(lambda: self.AGV_control_pressed_event('right'))
        self.right.released.connect(lambda: self.AGV_control_released_event('right'))

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
        
    def AGV_control_released_event(self, dir=None):
        if dir == 'up' or dir == 'down':
            self.x = 0.0
        elif dir == 'left' or dir == 'right':
            self.angle = 0.0
        if self.agv:
            self.control_event.set()
# End of AGV Speed Control
# AGV Navigation Control
    def init_navigation_tab(self):
        pass
    def map_combobox_change_path_box(self):
        self.PATH.clear()
        self.PATH.addItems(list(self.maps[self.MAP.currentText()].paths.keys()))
        Qmap = QPixmap()
        Qmap.loadFromData(self.agv.GET_map_png(self.MAP.currentText()), 'png')
        self.AGV_MAP_IMG.setPixmap(Qmap)
    def path_combobox_change_point_box(self):
        self.Point.clear()
        if self.PATH.currentText():
            ls = list(self.maps[self.MAP.currentText()].paths[self.PATH.currentText()].points.keys())
            ls.insert(0, 'auto')
            self.Point.addItems(ls)
    def start_close_navigation(self):
        # if button is checked
        if self.Start_Navigation.isChecked():
            # setting background color to light-blue
            self.Start_Navigation.setText('Cancel Navigation')
            self.Start_Navigation.setStyleSheet("background-color : lightgrey")
            if self.agv:
                self.Target_Navigation_Widget.show()
                self.Point_index.clear()
                self.Point_index.addItems(list(self.maps[self.MAP.currentText()].paths[self.PATH.currentText()].points.keys()))
                if self.Point.currentText() == 'auto':
                    self.agv.GET_start_navigation(self.MAP.currentText(), self.PATH.currentText())
                else:
                    self.agv.GET_start_navigation(self.MAP.currentText(), self.PATH.currentText(), self.maps[self.MAP.currentText()].paths[self.PATH.currentText()].points[self.Point.currentText()].index)
                
        # if it is unchecked
        else:
            # set background color back to light-grey
            self.Start_Navigation.setText('Start Navigation')
            self.Start_Navigation.setStyleSheet("background-color : white")
            if self.agv:
                self.Target_Navigation_Widget.hide()
                self.agv.GET_stop_navigation()
                self.nav_task_stat = False
                self.start_navigate_pt_button.setText('Start')
                self.start_navigate_pt_button.setStyleSheet("background-color : white")
                self.start_navigate_pt_button.setChecked(False)
                self.Navigation_Cancel.hide()
                
    def start_pause_navigation(self):
        if self.start_navigate_pt_button.isChecked():
            
            self.start_navigate_pt_button.setText('Pause')
            self.start_navigate_pt_button.setStyleSheet("background-color : lightgrey")
            self.Navigation_Cancel.show()
            if self.agv:
                if not self.nav_task_stat:
                    logging.debug('start navigation task')
                    result = self.agv.GET_navigation_move_to_index(self.maps[self.MAP.currentText()].paths[self.PATH.currentText()].points[self.Point_index.currentText()].index, self.MAP.currentText(), self.PATH.currentText())
                    self.nav_task_stat = True
                    self.currentTask_id = result['id']
                    thread = threading.Thread(target=self.AGV_check_task_status, args = (self.stop_navigation, self.currentTask_id, 0.5))
                    thread.start()
                else:
                    logging.debug('continue navigation task')
                    self.agv.GET_resume_task(self.currentTask_id)
        else:
            print('pause navigation task')
            self.start_navigate_pt_button.setText('Continue')
            self.start_navigate_pt_button.setStyleSheet("background-color : white")
            self.agv.GET_pause_task(self.currentTask_id)
    
    def stop_navigation(self):
        print('stop')
        self.start_navigate_pt_button.setText('Start')
        self.start_navigate_pt_button.setStyleSheet("background-color : white")
        self.start_navigate_pt_button.setChecked(False)
        self.Navigation_Cancel.hide()
        self.nav_task_stat = False
        self.agv.GET_stop_nav_task()
    # def start_nav_task(self):
    #     return
# End of AGV Navigation Control
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
    
    # Thread
    def AGV_info_thread(self, timeout):
        
        while not self.shutdown_event.is_set():
            
            self.SET_robot_info_to_app()
            self.shutdown_event.wait(timeout)
            
    def AGV_control_thread(self, timeout):
        flag = 0
        print('ok')
        while not self.shutdown_event.is_set():
            print('going')
            self.control_event.wait(timeout)
            x = self.x * self.speed
            angle = self.angle * self.speed
            self.agv.PUT_robot_speed(x, angle)
            self.control_event.clear()
            logging.info('speed_x: {}, speed_angle: {}, speed_factor: {}'.format(self.x, self.angle, self.speed))
            if x + angle == 0 and not flag:
                flag = 1
                self.control_event.wait()
            elif flag:
                flag = 0
    def AGV_check_task_status(self, func, id, timeout):
        while not self.shutdown_event.is_set():
            
            res = self.agv.GET_task(id)
            if res['current_task']['state'] == 'COMPLETE' or res['current_task']['state'] == 'CANCELLED':
                return func()
            self.shutdown_event.wait(timeout)
        
    
class Application():
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("simulator")
        self.window = MainWindow()
        self.app.exec_()


    

if __name__ == "__main__":
    app = Application()
    
    