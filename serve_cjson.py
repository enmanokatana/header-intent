
import sys

import cjson_pb2
import cjson_pb2_grpc

from src.emit.grpc_server import build_grpc_server

SO = "/tmp/cjson/libcjson.so"
SPEC = "cjson.spec.yaml"
PORT = 50051

if __name__ == "__main__":
    server = build_grpc_server(SO, SPEC, cjson_pb2, cjson_pb2_grpc,
                               service="CJson", port=PORT)
    server.start()
    print(f"[ferrule] cJSON gRPC server listening on :{PORT} (Ctrl+C to stop)",
          file=sys.stderr)
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=1)
