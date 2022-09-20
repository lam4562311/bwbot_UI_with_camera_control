import requests
import json
from socket import *
import time
import math
import logging


class agv():
    # auto connect existed lan network robot
    def __init__(self):
        self.udp_server = socket(AF_INET,SOCK_DGRAM)
        self.udp_server.bind(("0.0.0.0", 22002))
        self.udp_server.settimeout(60)
        data, addr = self.udp_server.recvfrom(1024)
        data = json.loads(data.decode("utf-8"))
        # logging.debug(json.dumps(data, indent=4))
        # get token
        self.robot_ip = addr[0]
        self.api_url = "http://{ip}:3546/api/v1".format(ip=self.robot_ip)
        res = requests.get("{api_url}/token?username=admin&password=admin".format(api_url=self.api_url))
        self.token = res.json()["token"]
        
    def get_request(self, URL, json=None):
        res = requests.get("{api_url}{URL}?token={token}".format(
            api_url=self.api_url, 
            URL = URL, 
            token = self.token
            )
            , json=json)
        content = res.json()
        logging.debug(content)
        return content
    
    def put_request(self, URL, json=None):
        logging.debug(json)
        res = requests.put("{api_url}{URL}?token={token}".format(
            api_url=self.api_url, 
            URL = URL, 
            token = self.token
            )
            , json=json)
        content = res.json()
        logging.debug(content)
        return content
        
    def GET_robot_info(self):
        '''
        {
        'battery': level, 
        'camera_rgb': topic_hz, 
        'camera_depth': topic_hz, 
        'odom': topic_hz, 
        'imu': topic_hz, 
        'camera_processed': 0=no data,
        'driver_port': E-stop stat, 
        'info': {
            'version': '6.1.4', 'code_name': 'chitu4.0-mboat', 'id': 'robot_id','mac': 'mac_address', 'port': 3546
        }, 
        'charge': bool, 
        'loop': False, 
        'slam_type': 'camera'
        }
        '''
        return self.get_request('/system/info')

    def GET_galileo_status(self):
        '''
        "navStatus":  # 导航服务状态，0表示没开启closed，1表示开启opened。
        "visualStatus":  # 视觉系统状态，-1标系视觉系统处于关闭状态，0表示没初始化uninit，1表示正在追踪tracking,2表示丢失lost,1和2都表示视觉系统已经初始化完成。
        "mapStatus":  # 建图服务状态，0表示未开始建图，1表示正在建图
        "gcStatus":  # 内存回收标志，0表示未进行内存回收，1表示正在进行内存回收
        "gbaStatus":  # 闭环优化标志，0表示未进行闭环优化，1表示正在进行闭环优化
        "chargeStatus":  # 充电状态，0 free 未充电状态, 1 charging 充电中, 2 charged 已充满，但仍在小电流充电, 3 finding 寻找充电桩, 4 docking 停靠充电桩, 5 error 错误
        "loopStatus":  # 是否处于自动巡检状态，1为处于，0为不处于。
        "power": # 电源电压v。
        "targetNumID":  # 当前目标点编号,默认值为-1表示无效值，当正在执行无ID的任务是值为-2，比如通过Http API 创建的导航任务。
        "targetStatus":  # 当前目标点状态，0表示已经到达或者取消free，1表示正在前往目标点过程中working,2表示当前目标点的移动任务被暂停paused,3表示目标点出现错误error,默认值为-1表示无效值。
        "targetDistance":  # 机器人距离当前目标点的距离，单位为米，-1表示无效值，该值的绝对值小于0.01时表示已经到达。
        "angleGoalStatus":  # 目标角度达到情况，0表示未完成，1表示完成，2表示error,默认值为-1表示无效值。
        "controlSpeedX":  # 导航系统计算给出的前进速度控制分量,单位为m/s。
        "controlSpeedTheta":  # 导航系统计算给出的角速度控制分量,单位为rad/s。
        "currentSpeedX": # 当前机器人实际前进速度分量,单位为m/s。
        "currentSpeedTheta": # 当前机器人实际角速度分量,单位为rad/s。
        "currentPosX":  # 当前机器人在map坐标系下的X坐标,此坐标可以直接用于设置动态插入点坐标
        "currentPosY":  # 当前机器人在map坐标系下的Y坐标
        "currentAngle":  # 当前机器人在map坐标系下的z轴转角(yaw)
        "busyStatus": #当busy为true时系统将仍然后接收新指令，但是不会立即处理。当系统退出busy状态后再处理消息
        '''
        return self.get_request('/system/galileo_status')
    
    def PUT_robot_speed(self, x = 0, y = 0, angle = 0):
        '''
        speed x     : forward and backward
        speed y     : left and right
        speed angle : turning clockwise and anti-clockwise
        ''' 
        
        return self.put_request('/system/speed', json = {
            "speed_x"       : x, 
            "speed_y"       : y, 
            "speed_angle"   : angle, 
        })
        
def main():
    asd  = agv()
    asd.PUT_robot_speed()
if __name__ == "__main__":
    main()