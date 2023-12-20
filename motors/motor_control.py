HOST = "localhost"
PORT = 4223
UID1 = "XYZ" # Replace with the UID of first Servo Bricklet
UID2 = "XYZ" # Replace with the UID of second Servo Bricklet
UID3 = "XYZ" # Replace with the UID of third Servo Bricklet

from tinkerforge.ip_connection import IPConnection
from tinkerforge.brick_hat import BrickHAT
from tinkerforge.bricklet_servo_v2 import BrickletServoV2
import rclpy
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectory
from datatypes.srv import MotorSettingsSrv
from datatypes.msg import MotorSettings, Error
from enum import Enum
from urllib import request as urllib_request, parse as urllib_parse, error as urllib_error
import json
                


class Motor:    
                
        def __init__(self, name, servo, ports, state, group):
                self.name = name
                self.servo = servo
                self.ports = ports
                self.state = state
                self.group = group

        def set_state(self, state):
                self.state = state

        def __str__(self):
                servo_id = "---"
                try:
                        servo_id = self.servo.get_identity()[0]
                except:
                        pass
                return f"(name = {self.name}, servo = {servo_id}, ports = {self.ports}, state = {self.state})"


class Group(Enum):
        left_hand = 0
        right_hand = 1
        left_arm = 2
        right_arm = 3
        head = 4
        none = 5



# receives a 'MotorSettings'-like, and returns a dict representing a motor-settings-json as it is used by the pib-api
def motor_settings_to_dto_dict(ms, motor):
        
        return {
                "name": motor.name,
                "turnedOn": ms.turned_on,
                "pulseWidthMin": ms.pulse_width_min,
                "pulseWidthMax": ms.pulse_width_max,
                "rotationRangeMin": ms.rotation_range_min,
                "rotationRangeMax": ms.rotation_range_max,
                "velocity": ms.velocity,
                "acceleration": ms.acceleration,
                "deceleration": ms.deceleration,
                "period": ms.period,
                "active": ms.active
        }



class Motor_control(Node):
                
        def __init__(self):

                qos_policy = rclpy.qos.QoSProfile(reliability=rclpy.qos.ReliabilityPolicy.BEST_EFFORT, history=rclpy.qos.HistoryPolicy.KEEP_LAST, depth=1)

                super().__init__('motor_control')

                # Toggle Devmode

                self.declare_parameter("dev", False)
                self.dev = self.get_parameter("dev").value

                # Topic for JointTrajectory
                self.subscription = self.create_subscription(
                        JointTrajectory,
                        'joint_trajectory',  # Topic name that Cerebra publishes to
                        self.joint_trajectory_callback,
                        qos_profile = qos_policy
                )
                                                                                                                                
                # Service for MotorSettings
                self.srv = self.create_service(
                        MotorSettingsSrv, 
                        'motor_settings', # Service name that Cerebra calls
                        self.motor_settings_callback
                )

                # Publisher for MotorSettings
                self.publisher = self.create_publisher(MotorSettings, "motor_settings", 10)
                # Connection
                self.ipcon = IPConnection()  # Create IP connection
                self.hat = BrickHAT("X", self.ipcon)
                self.ipcon.connect(HOST, 4223)

                temp = self.set_uid()
                self.get_logger().warn(f"{str(temp)}")
                
                # Handles for three Servo Bricklets
                self.servo1 = BrickletServoV2(UID1, self.ipcon)
                self.servo2 = BrickletServoV2(UID2, self.ipcon)
                self.servo3 = BrickletServoV2(UID3, self.ipcon)

                # Available motors
                self.motors = [
                        Motor("turn_head_motor", self.servo1, [0], True, 4),
                        Motor("tilt_forward_motor", self.servo1, [1], True, 4),
                        Motor("tilt_sideways_motor", self.servo1, [2], True, 4),
                        Motor("thumb_left_opposition", self.servo1, [3], True, 0),
                        Motor("thumb_left_stretch", self.servo1, [4], True, 0),
                        Motor("index_left_stretch", self.servo1, [5], True, 0),
                        Motor("middle_left_stretch", self.servo1, [6], True, 0),
                        Motor("ring_left_stretch", self.servo1, [7], True, 0),
                        Motor("pinky_left_stretch", self.servo1, [8], True, 0),
                        Motor("thumb_right_opposition", self.servo1, [9], True, 1),
                        Motor("thumb_right_stretch", self.servo2, [0], True, 1),
                        Motor("index_right_stretch", self.servo2, [1], True, 1),
                        Motor("middle_right_stretch", self.servo2, [2], True, 1),
                        Motor("ring_right_stretch", self.servo2, [3], True, 1),
                        Motor("pinky_right_stretch", self.servo2, [4], True, 1),
                        Motor("upper_arm_left_rotation", self.servo2, [5], True, 2),
                        Motor("elbow_left", self.servo2, [6], True, 2),
                        Motor("lower_arm_left_rotation", self.servo2, [7], True, 2),
                        Motor("wrist_left", self.servo2, [8], True, 2),
                        Motor("shoulder_vertical_left", self.servo3, [7, 9], True, 2),
                        Motor("shoulder_horizontal_left", self.servo3, [0], True, 2),
                        Motor("upper_arm_right_rotation", self.servo3, [1], True, 3),
                        Motor("elbow_right", self.servo3, [2], True, 3),
                        Motor("lower_arm_right_rotation", self.servo3, [3], True, 3),
                        Motor("wrist_right", self.servo3, [4], True, 3),
                        Motor("shoulder_vertical_right", self.servo3, [5, 8], True, 3),
                        Motor("shoulder_horizontal_right", self.servo3, [6], True, 3)
                ]       

                self.get_on_init_motor_settings_from_database()

                # Maps motor-name (as string) to motor-object
                self.motor_map = { motor.name : motor for motor in self.motors }

                # Log that initialization is complete
                self.get_logger().warn("Info: passed __init__")
                                                


        def motor_settings_callback(self, request, response):
                response.settings_persisted = False
                error = Error()
                try:

                        motors = self.motor_collection_to_multible_motors(request.motor_name)

                        if len(motors) == 0:
                                raise Exception("No motor found")

                        
                        for motor in motors:
                                try:
                                        for port in motor.ports:
                                                motor.servo.set_pulse_width(port, request.pulse_width_min, request.pulse_width_max)
                                                motor.servo.set_motion_configuration(port, request.velocity, request.acceleration, request.deceleration)
                                                motor.servo.set_period(port, request.period)
                                                motor.set_state(request.turned_on)
                                                motor.servo.set_degree(port, request.rotation_range_min, request.rotation_range_max)
                                        response.settings_applied = True
                                except Exception as e:
                                        response.settings_applied = False
                                        error.typ = "Motor settings error"
                                        error.message = f"Error applying motor-setting: {str(e)}"
                                        response.error = error
                                        return response

                                try: 
                                        if response.settings_applied == True :
                                                response.settings_persisted = self.persist_motor_settings_to_db(request, motor)
                                except Exception as e:
                                        self.get_logger().warn(f"Error persisting motor-setting: {str(e)}")
                                        response.settings_persisted = False
                                        error.typ = "Motor settings error"
                                        error.message = f"Error persisting motor-setting: {str(e)}"
                                        response.error = error
                                        return response

                except Exception as e:
                        self.get_logger().warn(f"Error processing motor-settings-message: {str(e)}")
                        response.settings_applied = False
                        error.typ = 'Motor settings error'
                        error.message = f"Error processing motor-settings-message: {str(e)}"
                        response.error = error
                        return response

                if self.dev == True or response.settings_applied == True:
                        #self.get_logger().info(f"Devmode: {str(self.dev)}\tresponse.settings_applied: {str(response.settings_applied)}")
                        msg = MotorSettings()
                        msg.motor_name = request.motor_name
                        msg.pulse_width_min = request.pulse_width_min
                        msg.pulse_width_max = request.pulse_width_max
                        msg.rotation_range_min = request.rotation_range_min
                        msg.rotation_range_max = request.rotation_range_max
                        msg.velocity = request.velocity
                        msg.acceleration = request.acceleration
                        msg.deceleration = request.deceleration
                        msg.active = request.active
                        msg.period = request.period
                        msg.turned_on = request.turned_on
                        self.publisher.publish(msg)
                return response
                


        def joint_trajectory_callback(self, msg):

                try:
                        motors = self.motor_collection_to_multible_motors(msg.joint_names[0])

                        if len(motors) == 0:
                                raise Exception("No motor found")
                        else:
                                for motor in motors:
                                        self.get_logger().info(f"Motor: {str(motor.name)}")
                                        value = msg.points[0].positions[0]

                                        if motor.name == "shoulder_vertical_left" or motor.name == "shoulder_vertical_right":
                                                value = value * -1

                                        self.get_logger().info(f"Value: {value}")
                                        for port in motor.ports:
                                                motor.servo.set_enable(port, motor.state)
                                                motor.servo.set_position(port, value)   

                except Exception as e:
                        self.get_logger().warn(f"Error processing joint-trajectory-message: {str(e)}")


                        
        def persist_motor_settings_to_db(self, motor_settings, motor):

                try:
                        # compile motor settings to UTF-8 encoded JSON string
                        http_req_body = json.dumps(motor_settings_to_dto_dict(motor_settings, motor)).encode('UTF-8'),
                        
                        # create 'PUT' request to '/motor-settings'
                        http_req = urllib_request.Request(
                                "http://localhost:5000/motor-settings",
                                method='PUT',
                                data=http_req_body,
                                headers={ "Content-Type": "application/json" }                           
                        )

                        # send request to pib-api
                        urllib_request.urlopen(http_req)
                        return True
                     
                except urllib_error.HTTPError as e: # if server response has 4XX or 5XX status code   
                        self.get_logger().warn(
                                f"Error sending HTTP-Request, received following response from server: \n" +
                                f"\tstatus: {e.code},\n" +
                                f"\treason: {e.reason},\n" +
                                f"\tresponse-body: {e.fp.read().decode()}" +
                                f"Request that caused the error:\n" +
                                f"\turl: {http_req.full_url},\n" +
                                f"\tmethod: {http_req.method},\n" +
                                f"\tbody: {http_req.data},\n" +
                                f"\theaders: {http_req.header_items()}"
                        )
                
                except Exception as e: # if something else fails
                        self.get_logger().warn(f"Error while sending HTTP-Request: {str(e)}")

                return False
        
        #Anpassen, dass alle motor Settings aus der DB beim initialisieren geholt werden
        def get_on_init_motor_settings_from_database(self):

                response = ""
        
                try:
                        for motor in self.motors:
                                
                                url = "http://localhost:5000/motor-settings/" + motor.name
                                headers = {"Content-Type": "application/json"}
                                http_req = urllib_request.Request(url, method='GET', headers=headers)

                                with urllib_request.urlopen(http_req) as response:
                                        
                                        response_data = response.read().decode('utf-8')
                                        
                                        response = json.loads(response_data)

                                if response['turnedOn'] == 1 or response['turnedOn'] == 'true' or response['turnedOn'] == 'True':
                                        motor.state = True
                                else:
                                        motor.state = False

                        return True
        
                except urllib_error.HTTPError as e: # if server response has 4XX or 5XX status code   
                        self.get_logger().warn(
                                f"Error sending HTTP-Request, received following response from server: \n" +
                                f"\tstatus: {e.code},\n" +
                                f"\treason: {e.reason},\n" +
                                f"\tresponse-body: {e.fp.read().decode()}" +
                                f"Request that caused the error:\n" +
                                f"\turl: {http_req.full_url},\n" +
                                f"\tmethod: {http_req.method},\n" +
                                f"\tbody: {http_req.data},\n" +
                                f"\theaders: {http_req.header_items()}"
                        )
                
                except Exception as e: # if something else fails
                        self.get_logger().warn(f"Error while getting initial motor settings: {str(e)}")

                return False
        
        def motor_collection_to_multible_motors(self, motor_name):

                if motor_name == "all_fingers_left":
                        return list(filter(lambda x: ("opposition" not in x.name and x.group == 0), self.motors))
                elif motor_name == "all_fingers_right":
                        return list(filter(lambda x: ("opposition" not in x.name and x.group == 1), self.motors))
                
                return [self.motor_map.get(motor_name)]
        

        def cb_enumerate(self, uid, connected_uid, position, hardware_version, firmware_version, device_identifier, enumeration_type):

                if position == "a":
                        global UID1
                        UID1 = uid
                if position == "b":
                        global UID2
                        UID2 = uid
                if position == "e":
                        global UID3
                        UID3 = uid

        def set_uid(self):
                self.ipcon.register_callback(IPConnection.CALLBACK_ENUMERATE, self.cb_enumerate)
                self.ipcon.enumerate()
                return "uid set"

        

def main(args=None):
        rclpy.init(args=args)
        motor_control = Motor_control()
        rclpy.spin(motor_control)
        rclpy.shutdown()
        motor_control.ipcon.disconnect()



if __name__ == '__main__':
        main()
