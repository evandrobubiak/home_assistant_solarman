import socket
import yaml
from homeassistant.util import Throttle
from datetime import datetime
from .parser import ParameterParser
from .const import *

START_OF_MESSAGE = 0xA5
END_OF_MESSAGE = 0x15
CONTROL_CODE = [0x10, 0x45]
SERIAL_NO = [0x00, 0x00]
SEND_DATA_FIELD = [0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

class Inverter:
    def __init__(self, path, serial, host, port, lookup_file):
        self._serial = serial
        self.path = path
        self._host = host
        self._port = port
        self._current_val = None
        self.status_connection = "Disconnected"
        self.status_lastUpdate = "N/A"
        if not lookup_file:
            lookup_file = 'parameters.yaml'
            
        with open(self.path + lookup_file) as f:
            self.parameter_definition = yaml.full_load(f) 

    def modbus(self, data):
        POLY = 0xA001

        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = ((crc >> 1) ^ POLY
                if (crc & 0x0001)
                else crc >> 1)  
        return crc    

    def get_serial_hex(self):
        serial_hex = hex(self._serial)[2:]
        serial_bytes = bytearray.fromhex(serial_hex)
        serial_bytes.reverse()
        return serial_bytes
    
    def get_read_business_field(self, start, length):
        request_data = bytearray([0x01, 0x03]) # Function Code
        request_data.extend(start.to_bytes(2, 'big'))
        request_data.extend(length.to_bytes(2, 'big'))
        crc = self.modbus(request_data)
        request_data.extend(crc.to_bytes(2, 'little'))  
        return request_data
        
    def generate_request(self, start, length):    
        packet = bytearray([START_OF_MESSAGE])

        packet_data = []
        packet_data.extend (SEND_DATA_FIELD)
        buisiness_field = self.get_read_business_field(start, length)
        packet_data.extend(buisiness_field)
        length = packet_data.__len__()
        packet.extend(length.to_bytes(2, "little")) 
        packet.extend(CONTROL_CODE)
        packet.extend(SERIAL_NO)
        packet.extend(self.get_serial_hex())    
        packet.extend(packet_data)
        #Checksum
        checksum = 0
        for i in range(1,len(packet),1):
            checksum += packet[i]
        packet.append(checksum & 0xFF)
        packet.append(END_OF_MESSAGE)  
        
        del packet_data      
        del buisiness_field
        return packet
 
    def send_request (self, params, start, end):
        length = end - start + 1
        request = self.generate_request(start, length)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        try:
            sock.connect((self._host, self._port))
            sock.sendall(request) # Request param 0x3B up to 0x71
            raw_msg = sock.recv(1024)
            self.status_lastUpdate = datetime.now().strftime("%m/%d/%Y, %H:%M:%S")
            self.status_connection = "Connected"
            params.parse(raw_msg, start, length) 
            del raw_msg
        except:
            print ('Could not connect to the inverter on %s:%s', self._host, self._port)
            self.status_connection = "Disconnected"
        finally:
            sock.close()
            
            del request
        return

    @Throttle (MIN_TIME_BETWEEN_UPDATES)
    def update (self):
        self.get_statistics()
        return


    def get_statistics(self):
        params = ParameterParser(self.parameter_definition)
        for request in self.parameter_definition['requests']:
            start = request['start']
            end= request['end']
            self.send_request(params, start, end)
        
        self._current_val = params.get_result()

    def get_current_val(self):
        return self._current_val

    def get_sensors(self):
        params = ParameterParser(self.parameter_definition)
        return params.get_sensors ()
