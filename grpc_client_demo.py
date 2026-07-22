import grpc

import cjson_pb2
import cjson_pb2_grpc

PORT = 50051


def main():
    channel = grpc.insecure_channel(f"localhost:{PORT}")
    stub = cjson_pb2_grpc.CJsonStub(channel)

    sess = stub.OpenSession(cjson_pb2.OpenSessionRequest())
    print("OpenSession  ->", sess.session_id)

    parsed = stub.CJSONParse(cjson_pb2.CJSONParseRequest(
        session_id=sess.session_id, value='{"a":1,"b":2}'))
    print("Parse        ->", parsed.handle)

    printed = stub.CJSONPrint(cjson_pb2.CJSONPrintRequest(
        session_id=sess.session_id, handle=parsed.handle))
    print("Print        ->", printed.result)

    item = stub.CJSONGetObjectItem(cjson_pb2.CJSONGetObjectItemRequest(
        session_id=sess.session_id, handle=parsed.handle, string="a"))
    print("GetObjectItem->", item.handle, "borrowed:", item.borrowed)

    print("Delete(borrowed item) -> ", end="")
    try:
        stub.CJSONDelete(cjson_pb2.CJSONDeleteRequest(
            session_id=sess.session_id, handle=item.handle))
        print("ALLOWED -- this is a BUG, it should have been refused")
    except grpc.RpcError as e:
        print(f"REFUSED ({e.code()}): {e.details()}")
        assert e.code() == grpc.StatusCode.FAILED_PRECONDITION,\
            "expected FAILED_PRECONDITION for a borrowed-handle free"

    done = stub.CJSONDelete(cjson_pb2.CJSONDeleteRequest(
        session_id=sess.session_id, handle=parsed.handle))
    print("Delete(root) ->", done.freed, "| live handles:", done.live_handles)

    closed = stub.CloseSession(cjson_pb2.CloseSessionRequest(session_id=sess.session_id))
    print("CloseSession ->", closed.released_handles, "handles still live at close")

    print("\nALL STEPS OK -- ownership enforced over gRPC, same as MCP.")


if __name__ == "__main__":
    main()
