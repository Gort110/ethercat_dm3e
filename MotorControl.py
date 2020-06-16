from CovEthercat import CovEthercatBasic
import time


class MotorControl(CovEthercatBasic):
    def __init__(self):
        super().__init__()
        self.mode_operation = 1
        self.target_acc = 5000000
        self.target_dec = 5000000
        self.target_vel = 30000000
        self.run()

    def MotorEnable(self):
        index = 0
        while 1:
            if index == 0:
                self.control_word = 0
                time.sleep(0.1)
                index = 1
            elif (index == 1) and (self.status_word & 0x250 == 0x250):
                self.control_word = 6
                time.sleep(0.1)
                index = 2
            elif (index == 2) and (self.status_word & 0x231 == 0x231):
                self.control_word = 7
                time.sleep(0.1)
                index = 3
            elif (index == 3) and (self.status_word & 0x233 == 0x233):
                self.control_word = 15
                time.sleep(0.1)
                index = 4
            elif (index == 4) and (self.status_word & 0x237 == 0x237):
                return True
            else:
                continue

    def MotorTargetPosition(self, position, moving_mode=True):
        index = 0
        self.mode_operation = 1
        self.target_position = position
        while 1:
            if self.mode_display == 1:
                if index == 0:
                    if moving_mode:
                        self.control_word = 0x0f
                    else:
                        self.control_word = 0x4f
                    time.sleep(0.1)
                    index = 1
                elif (index == 1) and (self.status_word & 0x8637 == 0x8637):
                    if moving_mode:
                        self.control_word = 0x1f
                    else:
                        self.control_word = 0x5f
                    time.sleep(0.1)
                    index = 2
                elif (index == 2) and (self.status_word & 0x1637 == 0x1637):
                    return True
                else:
                    continue

    def ZeroPosition(self):
        index = 0
        self.mode_operation = 6
        while 1:
            if self.mode_display == 6:
                if index == 0:
                    self.control_word = 0x1f
                    time.sleep(0.1)
                    index = 2
                elif (index == 2) and (self.status_word & 0x637 == 0x637):
                    return True
                else:
                    continue


DM3E522_control = MotorControl()
DM3E522_control.MotorEnable()
DM3E522_control.ZeroPosition()
DM3E522_control.MotorTargetPosition(400000)
DM3E522_control.close()




