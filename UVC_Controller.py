from distutils.log import debug
import sys
import logging
import ctypes as ct
import libusb as usb

# UVC 1.1 protocol supported
bmRequestType = 0b00100001          #D7：Transmit Direction
									#0=master to slave；1=slave to master
									#D6..5：type
									#0=std；1=type；
									#2=Manufacturer；3=reserved 
									#D4..0：recipient
									#0=device；1=interface ；
									#2=endpoint；3=other 
									#4..31 reserved
# bmRequestType = 0xA1              #receive
windex = 0x0100	# USB Interface descriptor-bInterfaceNumber value and Endpoint descriptor-bEndpointAddress value
# VENDOR_ID = 0x04B4
# DEVICE_ID = 0x00F9

MIN_ZOOM_ABS = 0x0000
MAX_ZOOM_ABS = 0x4000
MIN_PANTILT_SPEED = 0x03
MAX_PANTILT_SPEED = 0xFF


class UVCController:
    
    def __init__(self, vid, pid):
        self.ctx=None
        self.bRequest = {
            'SET_CUR'   : 0x01,
            'GET_CUR'   : 0x81,
            'GET_MIN'   : 0x82,
            'GET_MAX'   : 0x83,
            'GET_RES'   : 0x84,
            'GET_INFO'  : 0x86,
            'GET_DEF'   : 0x87
        }
        self.ControlSelector = {
            'CT_ZOOM_ABSOLUTE_CONTROL'      : 0x0b00,
            'CT_ZOOM_RELATIVE_CONTROL'      : 0x0c00,
            'CT_PANTILT_ABSOLUTE_CONTROL'   : 0x0d00,
            'CT_PANTILT_RELATIVE_CONTROL'   : 0x0e00
        }
        self.bmRequestType_send = 0x21
        self.bmRequestType_receive = 0xA1
        self.windex = windex
        self.r = usb.init(self.ctx)
        if self.r < 0:
            logging.error("failed to initialise libusb {} - {}".format(self.r, usb.strerror(self.r)))
        self.device = usb.open_device_with_vid_pid(self.ctx, ct.c_uint16(vid), ct.c_uint16(pid))
        if not self.device:
            logging.error("libusb_open_device() failed")
        usb.set_auto_detach_kernel_driver(self.device, 1)
        self.r = usb.claim_interface(self.device, 0)
        if self.r < 0:
            logging.error('Cannot Claim Interface failed with {} - {}'.format(self.r, usb.strerror(self.r)))
        logging.info('Claimed Interface')
    def __del__(self):
        self.r = usb.release_interface(self.device, 0)
        if self.r != 0:
            logging.error("Cannot Release Interface")
        logging.info("Released Interface")
        usb.close(self.device)
        usb.exit(self.ctx)
    
    def print_ct_ubyte_array(self, data):
        debug_str = 'data: '
        for i in range(ct.sizeof(data)):
            debug_str += " {:02x}".format(data[i])
        logging.debug(debug_str)
    def send_data(self, bmRequestType, bRequest, control_selector, windex, data, data_len, timeout):
        logging.info("Writing Data...")
        self.r = usb.control_transfer(self.device, bmRequestType, bRequest, control_selector, windex, data, data_len, timeout)
        if self.r == 0:
            logging.info("Writing Successful!")
        else:
            logging.warning("{} - {}".format(self.r, usb.strerror(self.r)))
    
#///////////////////////////////////////////////////////////////////
#//////////////////////Get Info From Camera/////////////////////////
#///////////////////////Not Implemented Yet/////////////////////////
#//////////////////End of Get Info From Camera//////////////////////
#///////////////////////////////////////////////////////////////////
#
#///////////////////////////////////////////////////////////////////
#///////////////////Get Capture From Camera/////////////////////////
#/////////////////////Not Implemented Yet///////////////////////////
#////////////////End of Get Capture From Camera/////////////////////
#///////////////////////////////////////////////////////////////////

#///////////////////////////////////////////////////////////////////
#//////////////////////////Zoom Control/////////////////////////////
    def ZoomAbsoluteControl(self, val): # uint16_t val
        control_selector = self.ControlSelector['CT_ZOOM_ABSOLUTE_CONTROL']
        request_type = self.bRequest['SET_CUR']
        data = (ct.c_ubyte * 2)(
            val, 
            val >> 8
        )
        
        self.print_ct_ubyte_array(data)
        self.send_data(self.bmRequestType_send, request_type, control_selector, self.windex, data, ct.sizeof(data), 0)
    
    def ZoomRelativeControl (self, Digital_Zoom, ZoomSpeed): # bool Digital_Zoom, int16_t ZoomSpeed
        control_selector = self.ControlSelector['CT_ZOOM_RELATIVE_CONTROL']
        request_type = self.bRequest['SET_CUR']
        
        if (ZoomSpeed == 0):
            data = (ct.c_ubyte * 3)(0, Digital_Zoom, 0)
        elif ZoomSpeed < 0:
            data = (ct.c_ubyte * 3)(0xff, Digital_Zoom, ZoomSpeed*-1)
        else:
            data = (ct.c_ubyte * 3)(0x01, Digital_Zoom, ZoomSpeed)
        
        self.print_ct_ubyte_array(data)
        self.send_data(self.bmRequestType_send, request_type, control_selector, self.windex, data, ct.sizeof(data), 0)
# //////////////////////End of Zoom Control//////////////////////////
# ///////////////////////////////////////////////////////////////////

# ///////////////////////////////////////////////////////////////////
# ////////////////////////Pan Tilt Control///////////////////////////
    def PanTiltAbsoluteControl(self, PanVal, TiltVal): #int PanVal, int TiltVal
        control_selector = self.ControlSelector['CT_PANTILT_ABSOLUTE_CONTROL']
        request_type = self.bRequest['SET_CUR']
        PanValRad = (PanVal)*3600
        TiltValRad = (TiltVal)*3600
        data = (ct.c_ubyte * 8)(
            PanValRad, 
            PanValRad >> 8, 
            PanValRad >> 16, 
            PanValRad >> 24, 
            TiltValRad, 
            TiltValRad >> 8, 
            TiltValRad >> 16, 
            TiltValRad >> 24
        )
        self.print_ct_ubyte_array(data)
        self.send_data(self.bmRequestType_send, request_type, control_selector, self.windex, data, ct.sizeof(data), 0)  
    def PanRelativeControl(self, PanSpeed): # int16_t PanSpeed
        control_selector = self.ControlSelector['CT_PANTILT_RELATIVE_CONTROL']
        request_type = self.bRequest['SET_CUR']
        
        if (PanSpeed == 0):
            data = (ct.c_ubyte * 4)(0)
        elif PanSpeed < 0:
            data = (ct.c_ubyte * 4)(0xff, PanSpeed*-1)
        else:
            data = (ct.c_ubyte * 4)(0x01, PanSpeed)
        self.print_ct_ubyte_array(data)
        self.send_data(self.bmRequestType_send, request_type, control_selector, self.windex, data, ct.sizeof(data), 0)
    def TiltRelativeControl(self, TiltSpeed): # int16_t TiltSpeed
        control_selector = self.ControlSelector['CT_PANTILT_RELATIVE_CONTROL']
        request_type = self.bRequest['SET_CUR']
        
        if (TiltSpeed == 0):
            data = (ct.c_ubyte * 4)(0)
        elif TiltSpeed < 0:
            data = (ct.c_ubyte * 4)(0, 0, 0xff, TiltSpeed*-1)
        else:
            data = (ct.c_ubyte * 4)(0, 0, 0x01, TiltSpeed)
        self.print_ct_ubyte_array(data)
        self.send_data(self.bmRequestType_send, request_type, control_selector, self.windex, data, ct.sizeof(data), 0)
    def PanTiltRelativeControl (self, PanSpeed, TiltSpeed): # int16_t PanSpeed, int16_t TiltSpeed
        control_selector = self.ControlSelector['CT_PANTILT_RELATIVE_CONTROL']
        request_type = self.bRequest['SET_CUR']
        data = (ct.c_ubyte * 4)(0)
        if PanSpeed < 0:
            data[0] = 0xff
            data[1] = PanSpeed*-1
        else:
            data[0] = 0x01
            data[1] = PanSpeed
        if TiltSpeed < 0:
            data[2] = 0xff
            data[3] = TiltSpeed*-1
        else:
            data[2] = 0x01
            data[3] = TiltSpeed
            
        self.print_ct_ubyte_array(data)
        self.send_data(self.bmRequestType_send, request_type, control_selector, self.windex, data, ct.sizeof(data), 0)
# ////////////////////End of Pan Tilt Control////////////////////////
# ///////////////////////////////////////////////////////////////////

def main():
    logging.basicConfig(level=logging.DEBUG,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] [%(module)s - %(funcName)s]: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler('debug.log')] )
    # UVC = UVCController(VENDOR_ID, DEVICE_ID)
    UVC = UVCController(0x04B4, 0x00F9)
    #custom control
    # UVC.ZoomAbsoluteControl(100)
    # UVC.ZoomRelativeControl(1, 255)
    # UVC.PanTiltAbsoluteControl(170,90)
    # UVC.PanRelativeControl(255)
    # UVC.TiltRelativeControl(255)
    UVC.PanTiltRelativeControl(255, 255)
    del UVC
    
if __name__ == "__main__":
    main()