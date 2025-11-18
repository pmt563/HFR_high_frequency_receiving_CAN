import logging
from typing import Optional
import can
import platform

log = logging.getLogger(__name__)

class CANMessage:
    def __init__(self, msg: can.Message):
        self.msg = msg

    def get_arbitration_id(self) -> int:
        return self.msg.arbitration_id

    def get_data(self):
        return self.msg.data

    def is_extended_id(self) -> bool:
        return self.msg.is_extended_id

    def get_timestamp(self):
        return self.msg.timestamp


class CANClient:
    def __init__(self, interface: str = "socketcan", channel: str = "vcan0", 
                 bitrate: int = 500000, port: int = None, fd: bool = False, **kwargs):
        self.interface = interface
        self.channel = channel
        self.bitrate = bitrate
        self.fd = fd
        
        log.info(f"Initializing CAN client: interface={interface}, channel={channel}, bitrate={bitrate}, fd={fd}")
        
        if interface == "kuksa":
            # KUKSA CAN provider configuration
            try:
                # Try to use kuksa_can_bridge if available
                from kuksa_can_bridge import CanClient
                self._kuksa_client = CanClient(
                    can_interface=channel,
                    can_bitrate=bitrate,
                    can_fd=fd
                )
                self._bus = self._kuksa_client.bus
                log.info(f"KUKSA CAN bus initialized: {channel} with bitrate {bitrate}, FD={fd}")
            except ImportError:
                log.warning("KUKSA CAN bridge not available, falling back to python-can")
                # Fallback to standard python-can with appropriate interface
                system = platform.system().lower()
                if system == "windows":
                    # On Windows, try PCAN or fallback to virtual
                    if "PCAN" in channel.upper():
                        self._bus = can.interface.Bus(interface="pcan", channel=channel, bitrate=bitrate, fd=fd, **kwargs)
                    else:
                        self._bus = can.interface.Bus(interface="virtual", channel=channel, bitrate=bitrate, **kwargs)
                else:
                    # On Linux, try socketcan
                    try:
                        self._bus = can.interface.Bus(interface="socketcan", channel=channel, bitrate=bitrate, fd=fd, **kwargs)
                    except Exception as e:
                        log.warning(f"SocketCAN failed: {e}, using virtual")
                        self._bus = can.interface.Bus(interface="virtual", channel=channel, bitrate=bitrate, **kwargs)
            except Exception as e:
                log.error(f"Failed to initialize KUKSA CAN: {e}, using virtual fallback")
                self._bus = can.interface.Bus(interface="virtual", channel=channel, bitrate=bitrate, **kwargs)
                
        elif interface == "udp_multicast":
            if port is None:
                raise ValueError("UDP multicast requires 'port' argument")
            self._bus = can.interface.Bus(
                interface="udp_multicast",
                channel=channel,
                port=port,
                bitrate=bitrate,
                **kwargs
            )
        else:
            # Direct python-can interface
            self._bus = can.interface.Bus(interface=interface, channel=channel, bitrate=bitrate, fd=fd, **kwargs)
        
        log.info(f"CAN bus initialized: {self._bus.channel_info}")

    def stop(self):
        try:
            if hasattr(self, '_kuksa_client') and self._kuksa_client:
                self._kuksa_client.stop()
            else:
                self._bus.shutdown()
            log.info("CAN client stopped successfully")
        except Exception as e:
            log.warning(f"Error shutting down CAN bus: {e}")

    def recv(self, timeout: Optional[float] = 1) -> Optional[CANMessage]:
        try:
            msg = self._bus.recv(timeout)
        except can.CanError as e:
            log.error(f"Error while waiting for recv from CAN: {e}")
            msg = None
        except Exception as e:
            log.error(f"Unexpected error receiving CAN message: {e}")
            msg = None
            
        if msg:
            return CANMessage(msg)
        return None

    def send(self, arbitration_id: int, data: bytes, is_extended_id: bool = False, is_fd: bool = None):
        if is_fd is None:
            is_fd = self.fd
            
        msg = can.Message(
            arbitration_id=arbitration_id, 
            data=data, 
            is_extended_id=is_extended_id,
            is_fd=is_fd
        )
        try:
            self._bus.send(msg)
            log.debug(f"CAN message sent: ID={arbitration_id:X}, Data={data.hex()}, FD={is_fd}")
        except can.CanError as e:
            log.error(f"Failed to send message via CAN bus: {e}")
        except Exception as e:
            log.error(f"Unexpected error sending CAN message: {e}")

    def send_message(self, message: CANMessage):
        """Send a CANMessage object"""
        try:
            self._bus.send(message.msg)
            log.debug(f"CAN message sent: ID={message.get_arbitration_id():X}")
        except can.CanError as e:
            log.error(f"Failed to send CANMessage via CAN bus: {e}")


def create_kuksa_client(channel: str = "PCAN_USBBUS1", bitrate: int = 500000, can_fd: bool = False, **kwargs) -> CANClient:
    """
    Factory function specifically for KUKSA CAN provider
    """
    return CANClient(interface="kuksa", channel=channel, bitrate=bitrate, fd=can_fd, **kwargs)


def create_default_client(channel: str = None, bitrate: int = 500000, can_fd: bool = False) -> CANClient:
    """
    Create appropriate CAN client based on platform
    """
    system = platform.system().lower()
    
    if channel is None:
        channel = "vcan0" if system != "windows" else "PCAN_USBBUS1"
    
    log.info(f"Creating default CAN client for system={system}, channel={channel}")
    
    try:
        if system == "windows":
            # On Windows, prefer KUKSA CAN provider with PCAN
            try:
                return create_kuksa_client(channel=channel, bitrate=bitrate, can_fd=can_fd)
            except Exception as e:
                log.warning(f"KUKSA CAN initialization failed: {e}")
                # Fallback to virtual interface
                return CANClient(interface="virtual", channel=channel, bitrate=bitrate, fd=can_fd)
        else:
            # On Linux, try socketcan first
            try:
                return CANClient(interface="socketcan", channel=channel, bitrate=bitrate, fd=can_fd)
            except Exception as e:
                log.warning(f"SocketCAN initialization failed: {e}")
                # Fallback to KUKSA or virtual
                try:
                    return create_kuksa_client(channel=channel, bitrate=bitrate, can_fd=can_fd)
                except Exception:
                    log.info("Using virtual CAN as fallback")
                    return CANClient(interface="virtual", channel=channel, bitrate=bitrate, fd=can_fd)
    except Exception as e:
        log.error(f"Failed to initialize CAN bus: {e}")
        log.info("Using virtual CAN as final fallback")
        return CANClient(interface="virtual", channel=channel, bitrate=bitrate, fd=can_fd)