"""Read-only, bounded access to this RF4 client's IL2CPP metadata.

Does not attach a debugger, inject code, or request memory write permissions.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import struct

GAME = Path(r"C:\Games\RF4\Game")


class ProcessEntry(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("pid", W.DWORD),
                ("heap", C.c_size_t), ("module", W.DWORD), ("threads", W.DWORD),
                ("parent", W.DWORD), ("priority", W.LONG), ("flags", W.DWORD), ("exe", W.WCHAR * 260)]


class ModuleEntry(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("module", W.DWORD), ("pid", W.DWORD),
                ("global_count", W.DWORD), ("process_count", W.DWORD),
                ("base", C.c_void_p), ("size", W.DWORD), ("handle", W.HMODULE),
                ("name", W.WCHAR * 256), ("path", W.WCHAR * 260)]


class Reader:
    def __init__(self):
        self.api = C.WinDLL("kernel32", use_last_error=True)
        declarations = {
            "CreateToolhelp32Snapshot": ([W.DWORD, W.DWORD], W.HANDLE),
            "CloseHandle": ([W.HANDLE], W.BOOL),
            "OpenProcess": ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            "QueryFullProcessImageNameW": ([W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL),
            "ReadProcessMemory": ([W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)], W.BOOL),
        }
        for name, (arguments, result) in declarations.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result
        self.handle = None
        self.total_bytes = 0
        processes = [p for p in self.entries(2, 0, ProcessEntry, "Process32FirstW", "Process32NextW")
                     if p.exe.lower() == "rf4_x64.exe"]
        if len(processes) != 1:
            raise RuntimeError("Expected exactly one RF4 client")
        self.pid = processes[0].pid
        self.handle = self.api.OpenProcess(0x1010, False, self.pid)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        try:
            buffer, size = C.create_unicode_buffer(32768), W.DWORD(32768)
            if not self.api.QueryFullProcessImageNameW(self.handle, 0, buffer, C.byref(size)):
                raise C.WinError(C.get_last_error())
            if Path(buffer.value).resolve() != (GAME / "rf4_x64.exe").resolve():
                raise ValueError("Target path mismatch")
            self.modules = {m.name: (m.base, m.size, m.path) for m in
                            self.entries(0x18, self.pid, ModuleEntry, "Module32FirstW", "Module32NextW")}
            base, _, path = self.modules["GameAssembly.dll"]
            if Path(path).resolve() != (GAME / "GameAssembly.dll").resolve():
                raise ValueError("GameAssembly path mismatch")
            self.base = base
        except Exception:
            self.close()
            raise

    def entries(self, flags, pid, entry_type, first_name, next_name):
        handle = self.api.CreateToolhelp32Snapshot(flags, pid)
        if handle == C.c_void_p(-1).value:
            raise C.WinError(C.get_last_error())
        functions = [getattr(self.api, n) for n in (first_name, next_name)]
        for function in functions:
            function.argtypes = [W.HANDLE, C.POINTER(entry_type)]
            function.restype = W.BOOL
        try:
            entry = entry_type()
            entry.dwSize = C.sizeof(entry)
            ok = functions[0](handle, C.byref(entry))
            while ok:
                yield entry_type.from_buffer_copy(entry)
                ok = functions[1](handle, C.byref(entry))
        finally:
            self.api.CloseHandle(handle)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def read(self, address: int, size: int) -> bytes:
        if not self.handle or not 0x10000 <= address < 0x7FFFFFFFFFFF or not 0 < size <= 65536:
            raise ValueError("Invalid bounded read")
        buffer, got = C.create_string_buffer(size), C.c_size_t()
        if not self.api.ReadProcessMemory(self.handle, address, buffer, size, C.byref(got)) or got.value != size:
            raise C.WinError(C.get_last_error())
        self.total_bytes += size
        return buffer.raw

    def ptr(self, address):
        return struct.unpack("<Q", self.read(address, 8))[0]

    def text(self, address, limit=256):
        value = self.read(address, limit).split(b"\0", 1)[0].decode("utf-8")
        if any(ord(c) < 32 for c in value):
            raise ValueError("Invalid metadata text")
        return value

    def rip_pointer(self, rva, prefix=b"\x48\x8b\x05"):
        address = self.base + rva
        code = self.read(address, 7)
        if code[:3] != prefix:
            raise ValueError("Client accessor changed")
        slot = address + 7 + struct.unpack_from("<i", code, 3)[0]
        if not self.base <= slot < self.base + self.modules["GameAssembly.dll"][1] - 8:
            raise ValueError("Global reference outside module")
        return self.ptr(slot)


PRIMITIVES = {1: "void", 2: "bool", 3: "char", 4: "sbyte", 5: "byte", 6: "short", 7: "ushort",
              8: "int", 9: "uint", 10: "long", 11: "ulong", 12: "float", 13: "double", 14: "string",
              24: "nint", 25: "nuint", 28: "object"}


class Metadata:
    def __init__(self, reader: Reader):
        self.reader = r = reader
        self.classes = {}
        self.type_names = {}
        self.field_cache = {}
        # Validate the accessors whose offsets are used below, from the IDA report.
        checks = {0x12480: b"\x48\x8b\x41\x10\xc3", 0x12AC0: b"\x48\x8b\x41\x18\xc3",
                  0x33A750: b"\x48\x8b\x41\x28\x44\x8b\x00"}
        for rva, expected in checks.items():
            if r.read(r.base + rva, len(expected)) != expected:
                raise ValueError("Unsupported client metadata layout")
        begin = r.rip_pointer(0x338C45)
        end = r.rip_pointer(0x338C30)
        if end < begin or (end - begin) % 8 or not 0 < (end - begin) // 8 <= 512:
            raise ValueError("Invalid assembly vector")
        self.assemblies = []
        table = r.rip_pointer(0x3619F0)
        for assembly in struct.unpack("<" + "Q" * ((end - begin) // 8), r.read(begin, end - begin)):
            image = r.ptr(assembly)
            header = r.read(image, 48)
            name = r.text(struct.unpack_from("<Q", header)[0], 128)
            count = struct.unpack_from("<I", header, 24)[0]
            handle = struct.unpack_from("<Q", header, 40)[0]
            start = struct.unpack("<i", r.read(handle, 4))[0]
            if not 0 <= start < 100000 or not 0 <= count <= 15000:
                raise ValueError("Invalid class range")
            self.assemblies.append(dict(name=name, count=count))
            for offset in range(0, count * 8, 65536):
                data = r.read(table + start * 8 + offset, min(65536, count * 8 - offset))
                for cls in struct.unpack("<" + "Q" * (len(data) // 8), data):
                    if not cls:
                        continue
                    try:
                        item = self.describe_class(cls)
                        item["assembly"] = name
                    except (OSError, ValueError):
                        continue

    def describe_class(self, address):
        if address in self.classes:
            return self.classes[address]
        r = self.reader
        raw = r.read(address, 0x128)
        name = r.text(struct.unpack_from("<Q", raw, 16)[0])
        namespace = r.text(struct.unpack_from("<Q", raw, 24)[0])
        data, bits = struct.unpack_from("<QI", raw, 32)
        item = dict(address=address, name=name, namespace=namespace,
                    full_name=namespace + "." + name if namespace else name,
                    type_data=data, type_code=(bits >> 16) & 255,
                    parent=struct.unpack_from("<Q", raw, 0x58)[0],
                    static_fields=struct.unpack_from("<Q", raw, 0xB8)[0],
                    methods_pointer=struct.unpack_from("<Q", raw, 0x98)[0],
                    method_count=struct.unpack_from("<H", raw, 0x120)[0],
                    field_pointer=struct.unpack_from("<Q", raw, 0x80)[0],
                    field_count=struct.unpack_from("<H", raw, 0x124)[0])
        self.classes[address] = item
        self.type_names[(data, item["type_code"])] = item["full_name"]
        return item

    def type_info(self, pointer, depth=0):
        raw = self.reader.read(pointer, 12)
        data, bits = struct.unpack("<QI", raw)
        code = (bits >> 16) & 255
        name = PRIMITIVES.get(code, self.type_names.get((data, code), f"type_{code:02x}"))
        if code == 21 and depth < 4:
            try:
                definition, instantiation, _, _ = struct.unpack("<QQQQ", self.reader.read(data, 32))
                inst = self.reader.read(instantiation, 16)
                count = struct.unpack_from("<I", inst)[0]
                arguments = struct.unpack_from("<Q", inst, 8)[0]
                if 0 < count <= 8:
                    argument_types = struct.unpack("<" + "Q" * count, self.reader.read(arguments, count * 8))
                    base = self.type_info(definition, depth + 1)["name"]
                    names = [self.type_info(p, depth + 1)["name"] for p in argument_types]
                    name = base + "<" + ", ".join(names) + ">"
            except (OSError, ValueError):
                pass
        return dict(code=code, attrs=bits & 65535, data=data, name=name)

    def fields(self, cls):
        if cls["address"] in self.field_cache:
            return self.field_cache[cls["address"]]
        count, pointer = cls["field_count"], cls["field_pointer"]
        if count > 1024:
            raise ValueError("Field count outside bounds")
        if not pointer:
            return []
        raw = self.reader.read(pointer, count * 32) if count else b""
        fields = []
        for index in range(count):
            name, type_pointer, parent, offset, token = struct.unpack_from("<QQQiI", raw, index * 32)
            if parent != cls["address"]:
                raise ValueError("Field parent mismatch")
            kind = self.type_info(type_pointer)
            fields.append(dict(name=self.reader.text(name, 128), offset=offset, type=kind["name"],
                               type_code=kind["code"], attrs=kind["attrs"], type_data=kind["data"],
                               is_static=bool(kind["attrs"] & 16), is_literal=bool(kind["attrs"] & 64)))
        self.field_cache[cls["address"]] = fields
        return fields

    def all_fields(self, cls):
        visited = set()
        while cls and cls["address"] not in visited:
            visited.add(cls["address"])
            yield from self.fields(cls)
            cls = self.describe_class(cls["parent"]) if cls["parent"] else None

    def methods(self, cls):
        count, pointer = cls["method_count"], cls["methods_pointer"]
        if count > 4096:
            raise ValueError("Method count outside bounds")
        if not pointer or not count:
            return []
        pointers = struct.unpack("<" + "Q" * count, self.reader.read(pointer, count * 8))
        result = []
        for method in pointers:
            raw = self.reader.read(method, 48)
            code, _, _, name_pointer, owner, return_type = struct.unpack("<QQQQQQ", raw)
            if owner != cls["address"]:
                raise ValueError("Method parent mismatch")
            result.append(dict(name=self.reader.text(name_pointer, 128),
                               rva=code - self.reader.base if code else None,
                               returns=self.type_info(return_type)["name"]))
        return result


if __name__ == "__main__":
    import json
    with Reader() as reader:
        metadata = Metadata(reader)
        targets = {"Fish", "Rod", "Reel", "Rig", "FishingSet", "RodRigFishingSet", "RodReelRigFishingSet",
                   "RigBobberBase", "RigBobberClassic", "FishingSceneBehaviour", "Fisher"}
        result = dict(pid=reader.pid, classes=len(metadata.classes), bytes_read=reader.total_bytes,
                      selected=[dict(name=c["full_name"], address=hex(c["address"]),
                                     parent=hex(c["parent"]), fields=metadata.fields(c))
                                for c in list(metadata.classes.values())
                                if c["namespace"] == "RF4.Client.FishingScene" and c["name"] in targets])
    Path(__file__).with_name("typed-metadata.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "selected"}, ensure_ascii=False))
