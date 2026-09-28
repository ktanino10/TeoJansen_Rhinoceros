"""Bound one owned CLI CAD process, preserving progress and failing explicitly."""

import argparse
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log",type=Path,required=True)
    parser.add_argument("--idle-limit",type=float,default=120)
    parser.add_argument("--total-limit",type=float,default=600)
    parser.add_argument("command",nargs=argparse.REMAINDER)
    args=parser.parse_args()
    command=args.command[1:] if args.command[:1]==["--"] else args.command
    if not command:raise ValueError("No CAD command supplied")
    args.log.parent.mkdir(parents=True,exist_ok=True)
    begin=last=time.monotonic()
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
    selector=selectors.DefaultSelector()
    selector.register(process.stdout,selectors.EVENT_READ)
    buffer=b""
    last_operation="startup"
    with args.log.open("wb") as stream:
        try:
            while True:
                now=time.monotonic()
                if now-begin>args.total_limit or now-last>args.idle_limit:
                    raise TimeoutError(f"CAD interval exceeded at {last_operation}; log={args.log}; PID={process.pid}")
                events=selector.select(timeout=1)
                for key,_ in events:
                    chunk=os.read(key.fileobj.fileno(),65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    stream.write(chunk);stream.flush()
                    buffer+=chunk
                    while b"\n" in buffer:
                        raw,buffer=buffer.split(b"\n",1)
                        text=raw.decode("utf-8",errors="replace")
                        if text.startswith(("BOOLEAN_BEGIN","BOOLEAN_END","STAGE_BEGIN","STAGE_END","UNION_BEGIN","UNION_END","MESH_DONE","define ","Building complete")):
                            last=time.monotonic()
                            last_operation=text
                        print(text,flush=True)
                if process.poll() is not None and not selector.get_map():
                    if buffer:print(buffer.decode("utf-8",errors="replace"),flush=True)
                    break
        except BaseException as error:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill();process.wait()
            receipt={"status":"FAILED","reason":str(error),"ownedPid":process.pid,
                     "lastOperation":last_operation,"elapsedSeconds":time.monotonic()-begin,
                     "log":str(args.log)}
            args.log.with_suffix(".failure.json").write_text(json.dumps(receipt,indent=2)+"\n")
            raise
        finally:
            selector.close()
    code=process.wait()
    if code:
        raise RuntimeError(f"CAD exited {code}; last={last_operation}; preserved log={args.log}")
    print(f"CAD_FINISHED {time.monotonic()-begin:.2f}s log={args.log}",flush=True)


if __name__=="__main__":
    main()
