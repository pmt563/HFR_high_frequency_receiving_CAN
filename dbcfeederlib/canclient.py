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


class CANClient:
    def __init__(self, interface: str = "socketcan", channel: str = "vcan0", bitrate: int = 500000, port: int = None, **kwargs):
        self.interface = interface
        self.channel = channel
        
        if interface == "kuksa":
            # KUKSA CAN provider configuration
            try:
                from kuksa_can_bridge import CanClient
                self._kuksa_client = CanClient(
                    can_interface=channel,
                    can_bitrate=bitrate
                )
                self._bus = self._kuksa_client.bus
                log.info(f"KUKSA CAN bus initialized: {channel} with bitrate {bitrate}")
            except ImportError:
                log.error("KUKSA CAN provider not available. Falling back to virtual interface.")
                self._bus = can.interface.Bus(interface="virtual", channel=channel)
            except Exception as e:
                log.error(f"Failed to initialize KUKSA CAN: {e}")
                self._bus = can.interface.Bus(interface="virtual", channel=channel)
                
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
            self._bus = can.interface.Bus(interface=interface, channel=channel, bitrate=bitrate, **kwargs)
        
        log.info(f"CAN bus initialized: {self._bus.channel_info}")

    def stop(self):
        try:
            if hasattr(self, '_kuksa_client') and self._kuksa_client:
                self._kuksa_client.stop()
            else:
                self._bus.shutdown()
        except Exception as e:
            log.warning(f"Error shutting down CAN bus: {e}")

    def recv(self, timeout: int = 1) -> Optional[CANMessage]:
        try:
            msg = self._bus.recv(timeout)
        except can.CanError:
            msg = None
            log.error("Error while waiting for recv from CAN", exc_info=True)
        if msg:
            return CANMessage(msg)
        return None

    def send(self, arbitration_id, data):
        msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=False)
        try:
            self._bus.send(msg)
        except can.CanError as e:
            log.error(f"Failed to send message via CAN bus: {e}")


def create_default_client(channel: str = "vcan0", bitrate: int = 500000) -> CANClient:
    system = platform.system().lower()
    log.info(f"create_default_client for system={system}")

    try:
        if system == "windows":
            # Try KUKSA CAN provider first on Windows
            try:
                return CANClient(
                    interface="kuksa",
                    channel=channel,  # e.g., "PCAN_USBBUS1", "CAN0", etc.
                    bitrate=bitrate
                )
            except Exception as kuksa_error:
                log.warning(f"KUKSA CAN initialization failed: {kuksa_error}")
                log.info("Falling back to UDP multicast")
                # Fallback to UDP multicast
                return CANClient(
                    interface="udp_multicast",
                    channel="239.0.0.1",  # multicast IP
                    port=50000            # multicast port
                )
        else:
            # Linux - try socketcan first, then KUKSA as fallback
            try:
                return CANClient(interface="socketcan", channel=channel, bitrate=bitrate)
            except Exception as socketcan_error:
                log.warning(f"SocketCAN initialization failed: {socketcan_error}")
                log.info("Trying KUKSA CAN as fallback")
                return CANClient(interface="kuksa", channel=channel, bitrate=bitrate)
    except Exception as e:
        log.error(f"Failed to initialize CAN bus: {e}")
        log.info("Using virtual CAN as fallback (isolated per-process).")
        return CANClient(interface="virtual")


def create_kuksa_client(channel: str = "vcan0", bitrate: int = 500000, **kwargs) -> CANClient:
    """
    Factory function specifically for KUKSA CAN provider
    """
    return CANClient(interface="kuksa", channel=channel, bitrate=bitrate, **kwargs)


def create_pcan_client(channel: str = "PCAN_USBBUS1", bitrate: int = 500000) -> CANClient:
    """
    Factory function for PCAN devices with KUKSA
    """
    return create_kuksa_client(channel=channel, bitrate=bitrate)