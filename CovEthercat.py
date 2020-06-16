import sys
import struct
import time
import threading
from collections import namedtuple
import pysoem

HostIfname = '\\Device\\NPF_{E93B5339-FA89-43C5-A31C-ACDD0814344F}'


class CovEthercatBasic:

    LEISEI_ID = 17185
    DM3E_522_PRODUCT_CODE = 33536

    def __init__(self):
        self._ifname = HostIfname
        self._pd_thread_stop_event = threading.Event()
        self._ch_thread_stop_event = threading.Event()
        self.pd_thread = 0
        self.ch_thread = 0
        self._actual_wkc = 0
        self._master = pysoem.Master()
        self._master.in_op = False
        self._master.do_check_state = False
        SlaveSet = namedtuple('SlaveSet', 'name product_code config_func')
        self._expected_slave_layout = {0: SlaveSet('DM3E-522', self.DM3E_522_PRODUCT_CODE, self.dm3e522_setup)}
        self.control_word = 0
        self.target_position = 0
        self.target_vel = 0
        self.target_acc = 0
        self.target_dec = 0
        self.mode_operation = 0
        self.last_error = 0
        self.status_word = 0
        self.mode_display = 0
        self.actual_position = 0
        self.touch_probe_status = 0
        self.touch_probe_value = 0
        self.digital_input = 0

    def dm3e522_setup(self, slave_pos):
        slave = self._master.slaves[slave_pos]
        tx_map_1c13_bytes = struct.pack('BxH', 1, 0x1A00)
        slave.sdo_write(0x1c13, 0, tx_map_1c13_bytes, True)
        rx_map_1c12 = [0x1601]
        rx_map_1c12_bytes = struct.pack('Bx' + ''.join(['H' for i in range(len(rx_map_1c12))]), len(rx_map_1c12),
                                        *rx_map_1c12)
        slave.sdo_write(0x1c12, 0, rx_map_1c12_bytes, True)

        # add max current set
        current_max = 800
        slave.sdo_write(0x2000, 0, struct.pack("H", current_max))
        # set mode of the back zero
        zero_position = 17
        slave.sdo_write(0x6098, 0, struct.pack("B", zero_position))
        slave.dc_sync(1, 10000000)

    def _processdata_thread(self):
        while not self._pd_thread_stop_event.is_set():
            self.last_error, self.status_word, self.mode_display, self.actual_position, self.touch_probe_status, \
                self.touch_probe_value, self.digital_input = struct.unpack("<2HBiHiI", self._master.slaves[0].input)
            self._master.slaves[0].output = struct.pack("<Hi3IB",
                                                        self.control_word, self.target_position,
                                                        self.target_vel, self.target_acc,
                                                        self.target_dec, self.mode_operation)
            self._master.send_processdata()
            self._actual_wkc = self._master.receive_processdata(10000)
            if not self._actual_wkc == self._master.expected_wkc:
                print('incorrect wkc')

    def _pdo_update_loop(self):
        self._master.in_op = True
        try:
            while 1:
                self.last_error, self.status_word, self.mode_display, self.actual_position, self.touch_probe_status, \
                    self.touch_probe_value, self.digital_input = struct.unpack("<2HBiHiI", self._master.slaves[0].input)
                self._master.slaves[0].output = struct.pack("<Hi3IB",
                                                            self.control_word, self.target_position,
                                                            self.target_vel, self.target_acc,
                                                            self.target_dec, self.mode_operation)
                time.sleep(1)
        except KeyboardInterrupt:
            # ctrl-C abort handling
            print('stopped')

    def run(self):
        self._master.open(self._ifname)

        if not self._master.config_init() > 0:
            self._master.close()
            raise CovEthercatBasicError('no slave found')

        for i, slave in enumerate(self._master.slaves):
            if not ((slave.man == self.LEISEI_ID) and
                    (slave.id == self._expected_slave_layout[i].product_code)):
                self._master.close()
                raise CovEthercatBasicError('unexpected slave layout')
            slave.config_func = self._expected_slave_layout[i].config_func
            slave.is_lost = False

        self._master.config_map()

        if self._master.state_check(pysoem.SAFEOP_STATE, 50000) != pysoem.SAFEOP_STATE:
            self._master.close()
            raise CovEthercatBasicError('not all slaves reached SAFEOP state')

        self._master.state = pysoem.OP_STATE

        self.ch_thread = threading.Thread(target=self._check_thread)
        self.ch_thread.start()
        self.pd_thread = threading.Thread(target=self._processdata_thread)
        self.pd_thread.start()
        self._master.write_state()
        all_slaves_reached_op_state = False
        for i in range(40):
            self._master.state_check(pysoem.OP_STATE, 50000)
            if self._master.state == pysoem.OP_STATE:
                all_slaves_reached_op_state = True
                break
        # if not all_slaves_reached_op_state:
        #     self._pdo_update_loop()
        if not all_slaves_reached_op_state:
            raise CovEthercatBasicError('not all slaves reached OP state')

    def close(self):
        self._pd_thread_stop_event.set()
        self._ch_thread_stop_event.set()
        self.ch_thread.join()
        self.pd_thread.join()
        self._master.state = pysoem.INIT_STATE
        self._master.write_state()
        self._master.close()

    @staticmethod
    def _check_slave(slave, pos):
        if slave.state == (pysoem.SAFEOP_STATE + pysoem.STATE_ERROR):
            print(
                'ERROR : slave {} is in SAFE_OP + ERROR, attempting ack.'.format(pos))
            slave.state = pysoem.SAFEOP_STATE + pysoem.STATE_ACK
            slave.write_state()
        elif slave.state == pysoem.SAFEOP_STATE:
            print(
                'WARNING : slave {} is in SAFE_OP, try change to OPERATIONAL.'.format(pos))
            slave.state = pysoem.OP_STATE
            slave.write_state()
        elif slave.state > pysoem.NONE_STATE:
            if slave.reconfig():
                slave.is_lost = False
                print('MESSAGE : slave {} reconfigured'.format(pos))
        elif not slave.is_lost:
            slave.state_check(pysoem.OP_STATE)
            if slave.state == pysoem.NONE_STATE:
                slave.is_lost = True
                print('ERROR : slave {} lost'.format(pos))
        if slave.is_lost:
            if slave.state == pysoem.NONE_STATE:
                if slave.recover():
                    slave.is_lost = False
                    print(
                        'MESSAGE : slave {} recovered'.format(pos))
            else:
                slave.is_lost = False
                print('MESSAGE : slave {} found'.format(pos))

    def _check_thread(self):
        while not self._ch_thread_stop_event.is_set():
            if self._master.in_op and ((self._actual_wkc < self._master.expected_wkc) or self._master.do_check_state):
                self._master.do_check_state = False
                self._master.read_state()
                for i, slave in enumerate(self._master.slaves):
                    if slave.state != pysoem.OP_STATE:
                        self._master.do_check_state = True
                        self._check_slave(slave, i)
                if not self._master.do_check_state:
                    print('OK : all slaves resumed OPERATIONAL.')


class CovEthercatBasicError(Exception):
    def __init__(self, message):
        super(CovEthercatBasicError, self).__init__(message)
        self.message = message


if __name__ == '__main__':
    print('CovEthercatBasic started')
    try:
        CovEthercatBasic().run()
    except CovEthercatBasicError as expt:
        print('CovEthercatBasic failed: ' + expt.message)
