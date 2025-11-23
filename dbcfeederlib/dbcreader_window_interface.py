#!/usr/bin/python3

########################################################################
# Copyright (c) 2020,2023 Contributors to the Eclipse Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0
########################################################################

import threading
import logging
import platform  # THÊM IMPORT NÀY

from queue import Queue
from typing import Optional

from dbcfeederlib.canclient import CANClient, create_default_client
from dbcfeederlib import canreader
from dbcfeederlib import dbc2vssmapper

log = logging.getLogger(__name__)


class DBCReader(canreader.CanReader):
    def __init__(self, rxqueue: Queue, mapper: dbc2vssmapper.Mapper, can_port: str,
                 can_fd: bool, dump_file: Optional[str] = None):
        super().__init__(rxqueue, mapper, can_port, dump_file, can_fd=can_fd)

    def _rx_worker(self):

        log.info("Starting to receive CAN messages fom bus")
        while self.is_running():
            msg = self._canclient.recv(timeout=1)
            if msg is not None:
                log.debug("Processing CAN message with frame ID %#x", msg.get_arbitration_id())
                log.debug("Type of ID: %s - data:%s", type(msg.get_arbitration_id()), type(msg.get_data()))
                self._process_can_message(msg.get_arbitration_id(), msg.get_data())
        log.info("Stopped receiving CAN messages from bus")

    def _start_can_bus_listener(self):
        try:
            # THÊM XỬ LÝ LỖI VÀ FALLBACK
            system = platform.system().lower()
            if system == "windows":
                # Trên Windows, ưu tiên dùng virtual interface
                try:
                    self._canclient = create_default_client(
                        channel=self._can_kwargs["channel"],
                        bitrate=500000,
                        can_fd=self._can_kwargs.get("fd", False)
                    )
                    log.info("✓ Using default CAN client for Windows")
                except Exception as e:
                    log.error(f"Failed to create default CAN client: {e}")
                    # Fallback cuối cùng
                    self._canclient = CANClient(interface="virtual", channel="virtual_channel", bitrate=500000)
                    log.info("✓ Using virtual CAN client as fallback")
            else:
                # Trên Linux, dùng tham số bình thường
                self._canclient = CANClient(**self._can_kwargs)
                
        except Exception as e:
            log.error(f"Failed to initialize CAN client: {e}")
            # Fallback cuối cùng
            self._canclient = CANClient(interface="virtual", channel="virtual_channel", bitrate=500000)
            log.info("✓ Using virtual CAN client as final fallback")
            
        rx_thread = threading.Thread(target=self._rx_worker)
        rx_thread.start()
        log.info("[_DBC_reader.rx_thread] Started CAN bus listener thread %s", rx_thread.name)
        log.info("Thread id: %s", rx_thread.ident)

    def _stop_can_bus_listener(self):
        self._canclient.stop()
        log.info("Stopped CAN bus listener thread %s", threading.current_thread().name)