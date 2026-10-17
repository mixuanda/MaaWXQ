"""Future IPC/native adapter boundaries. This module opens no connection or process."""
from typing import Protocol


class ControlTransport(Protocol):
    scope: str
    connected: bool

    def receive(self, max_bytes: int = 4096) -> bytes | None:
        """Future bounded local-IPC read. Peer ACL/identity validation belongs to the adapter."""
        ...
    def close(self) -> None: ...


class NativeInputPort(Protocol):
    scope: str
    connected: bool

    def observe_binding(self): ...
    def emit(self, action, permit) -> bool:
        """Check permit immediately before irreversible submission; False means no submission."""
        ...
    def release(self, operation: str, code: int, binding_digest: str) -> bool: ...
    def close(self) -> None: ...


class DisconnectedTransport:
    scope = "unconnected"
    connected = False

    def receive(self, max_bytes=4096):
        raise RuntimeError("control_transport_not_connected")

    def close(self):
        self.connected = False


class DisconnectedInput:
    scope = "unconnected"
    connected = False

    def observe_binding(self):
        raise RuntimeError("native_input_not_connected")

    def emit(self, action, permit):
        raise RuntimeError("native_input_not_implemented")

    def release(self, operation, code, binding_digest):
        raise RuntimeError("native_release_not_implemented")

    def close(self):
        self.connected = False
