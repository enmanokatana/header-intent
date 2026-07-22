from __future__ import annotations

from .proto import make_servicer, pascal
from ..core.handles import OwnershipError


def build_grpc_servicer(so_path: str, spec_path_or_spec, pb2, pb2_grpc, service: str):
    """Return an instance of the generated `{service}Servicer` base class whose
    methods call the real C library through the protocol-agnostic core."""
    import grpc

    ferrule_srv = make_servicer(so_path, spec_path_or_spec)
    base_cls = getattr(pb2_grpc, f"{service}Servicer")

    def wrap(py_method, response_name: str):
        response_cls = getattr(pb2, response_name)

        def method(self, request, context):
            try:
                result = py_method(request, context)
            except OwnershipError as e:
                                                                             
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
            except PermissionError as e:                                        
                context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))
            except KeyError as e:
                context.abort(grpc.StatusCode.NOT_FOUND, str(e))
            except Exception as e:                                    
                context.abort(grpc.StatusCode.INTERNAL, f"{type(e).__name__}: {e}")
                                                                
            valid = set(response_cls.DESCRIPTOR.fields_by_name)
            return response_cls(**{k: v for k, v in result.items()
                                   if k in valid and v is not None})

        return method

    attrs = {
        "OpenSession": wrap(ferrule_srv.OpenSession, "OpenSessionResponse"),
        "CloseSession": wrap(ferrule_srv.CloseSession, "CloseSessionResponse"),
    }
    for name in ferrule_srv.capability_names:
        attrs[name] = wrap(getattr(ferrule_srv, name), f"{name}Response")

    GrpcServicer = type(f"{service}GrpcServicer", (base_cls,), attrs)
    servicer = GrpcServicer()
    servicer.refused_functions = ferrule_srv.refused_functions                
    servicer.capability_names = ferrule_srv.capability_names                  
    return servicer


def build_grpc_server(so_path: str, spec_path_or_spec, pb2, pb2_grpc, service: str,
                      port: int = 50051, max_workers: int = 8):
    """Build (but do not start) a ready-to-serve grpc.Server."""
    import sys
    import grpc
    from concurrent import futures

    servicer = build_grpc_servicer(so_path, spec_path_or_spec, pb2, pb2_grpc, service)
    if servicer.refused_functions:
        print(f"[ferrule] skipped {len(servicer.refused_functions)} refused "
              f"(fail-safe):", file=sys.stderr)
        for n, why in servicer.refused_functions:
            print(f"  - {n}: {why}", file=sys.stderr)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    add_fn = getattr(pb2_grpc, f"add_{service}Servicer_to_server")
    add_fn(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    print(f"[ferrule] serving {service} on port {port} "
          f"({len(servicer.capability_names)} capabilities)", file=sys.stderr)
    return server