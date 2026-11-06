import asyncio
from winsdk.windows.networking.connectivity import NetworkInformation
from winsdk.windows.networking.networkoperators import NetworkOperatorTetheringManager

async def main():
    profile = NetworkInformation.get_internet_connection_profile()
    tm = NetworkOperatorTetheringManager.create_from_connection_profile(profile)
    cfg = tm.get_current_access_point_configuration()
    print("ssid", cfg.ssid)
    print("tm", [m for m in dir(tm) if not m.startswith("_")])
    print("cfg", [m for m in dir(cfg) if not m.startswith("_")])
    r = await tm.start_tethering_async()
    print("result attrs", [m for m in dir(r) if not m.startswith("_")])
    print("status", getattr(r, "status", None), "error", getattr(r, "additional_error_code", None))
    await asyncio.sleep(1)
    r2 = await tm.stop_tethering_async()
    print("stop status", r2.status)

asyncio.run(main())
