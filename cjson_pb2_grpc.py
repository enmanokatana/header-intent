                                                                     
import grpc
import warnings

import cjson_pb2 as cjson__pb2

GRPC_GENERATED_VERSION = '1.82.1'
GRPC_VERSION = grpc.__version__
_version_not_supported = False

try:
    from grpc._utilities import first_version_is_lower
    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
except ImportError:
    _version_not_supported = True

if _version_not_supported:
    raise RuntimeError(
        f'The grpc package installed is at version {GRPC_VERSION},'
        + ' but the generated code in cjson_pb2_grpc.py depends on'
        + f' grpcio>={GRPC_GENERATED_VERSION}.'
        + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}'
        + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.'
    )


class CJsonStub:
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.OpenSession = channel.unary_unary(
                '/cjson.CJson/OpenSession',
                request_serializer=cjson__pb2.OpenSessionRequest.SerializeToString,
                response_deserializer=cjson__pb2.OpenSessionResponse.FromString,
                _registered_method=True)
        self.CloseSession = channel.unary_unary(
                '/cjson.CJson/CloseSession',
                request_serializer=cjson__pb2.CloseSessionRequest.SerializeToString,
                response_deserializer=cjson__pb2.CloseSessionResponse.FromString,
                _registered_method=True)
        self.CJSONVersion = channel.unary_unary(
                '/cjson.CJson/CJSONVersion',
                request_serializer=cjson__pb2.CJSONVersionRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONVersionResponse.FromString,
                _registered_method=True)
        self.CJSONParse = channel.unary_unary(
                '/cjson.CJson/CJSONParse',
                request_serializer=cjson__pb2.CJSONParseRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONParseResponse.FromString,
                _registered_method=True)
        self.CJSONParseWithLength = channel.unary_unary(
                '/cjson.CJson/CJSONParseWithLength',
                request_serializer=cjson__pb2.CJSONParseWithLengthRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONParseWithLengthResponse.FromString,
                _registered_method=True)
        self.CJSONPrint = channel.unary_unary(
                '/cjson.CJson/CJSONPrint',
                request_serializer=cjson__pb2.CJSONPrintRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONPrintResponse.FromString,
                _registered_method=True)
        self.CJSONPrintUnformatted = channel.unary_unary(
                '/cjson.CJson/CJSONPrintUnformatted',
                request_serializer=cjson__pb2.CJSONPrintUnformattedRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONPrintUnformattedResponse.FromString,
                _registered_method=True)
        self.CJSONPrintBuffered = channel.unary_unary(
                '/cjson.CJson/CJSONPrintBuffered',
                request_serializer=cjson__pb2.CJSONPrintBufferedRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONPrintBufferedResponse.FromString,
                _registered_method=True)
        self.CJSONDelete = channel.unary_unary(
                '/cjson.CJson/CJSONDelete',
                request_serializer=cjson__pb2.CJSONDeleteRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONDeleteResponse.FromString,
                _registered_method=True)
        self.CJSONGetArraySize = channel.unary_unary(
                '/cjson.CJson/CJSONGetArraySize',
                request_serializer=cjson__pb2.CJSONGetArraySizeRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONGetArraySizeResponse.FromString,
                _registered_method=True)
        self.CJSONGetArrayItem = channel.unary_unary(
                '/cjson.CJson/CJSONGetArrayItem',
                request_serializer=cjson__pb2.CJSONGetArrayItemRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONGetArrayItemResponse.FromString,
                _registered_method=True)
        self.CJSONGetObjectItem = channel.unary_unary(
                '/cjson.CJson/CJSONGetObjectItem',
                request_serializer=cjson__pb2.CJSONGetObjectItemRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONGetObjectItemResponse.FromString,
                _registered_method=True)
        self.CJSONGetObjectItemCaseSensitive = channel.unary_unary(
                '/cjson.CJson/CJSONGetObjectItemCaseSensitive',
                request_serializer=cjson__pb2.CJSONGetObjectItemCaseSensitiveRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONGetObjectItemCaseSensitiveResponse.FromString,
                _registered_method=True)
        self.CJSONHasObjectItem = channel.unary_unary(
                '/cjson.CJson/CJSONHasObjectItem',
                request_serializer=cjson__pb2.CJSONHasObjectItemRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONHasObjectItemResponse.FromString,
                _registered_method=True)
        self.CJSONGetErrorPtr = channel.unary_unary(
                '/cjson.CJson/CJSONGetErrorPtr',
                request_serializer=cjson__pb2.CJSONGetErrorPtrRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONGetErrorPtrResponse.FromString,
                _registered_method=True)
        self.CJSONGetStringValue = channel.unary_unary(
                '/cjson.CJson/CJSONGetStringValue',
                request_serializer=cjson__pb2.CJSONGetStringValueRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONGetStringValueResponse.FromString,
                _registered_method=True)
        self.CJSONGetNumberValue = channel.unary_unary(
                '/cjson.CJson/CJSONGetNumberValue',
                request_serializer=cjson__pb2.CJSONGetNumberValueRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONGetNumberValueResponse.FromString,
                _registered_method=True)
        self.CJSONIsInvalid = channel.unary_unary(
                '/cjson.CJson/CJSONIsInvalid',
                request_serializer=cjson__pb2.CJSONIsInvalidRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONIsInvalidResponse.FromString,
                _registered_method=True)
        self.CJSONIsFalse = channel.unary_unary(
                '/cjson.CJson/CJSONIsFalse',
                request_serializer=cjson__pb2.CJSONIsFalseRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONIsFalseResponse.FromString,
                _registered_method=True)
        self.CJSONIsTrue = channel.unary_unary(
                '/cjson.CJson/CJSONIsTrue',
                request_serializer=cjson__pb2.CJSONIsTrueRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONIsTrueResponse.FromString,
                _registered_method=True)
        self.CJSONIsBool = channel.unary_unary(
                '/cjson.CJson/CJSONIsBool',
                request_serializer=cjson__pb2.CJSONIsBoolRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONIsBoolResponse.FromString,
                _registered_method=True)
        self.CJSONIsNull = channel.unary_unary(
                '/cjson.CJson/CJSONIsNull',
                request_serializer=cjson__pb2.CJSONIsNullRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONIsNullResponse.FromString,
                _registered_method=True)
        self.CJSONIsNumber = channel.unary_unary(
                '/cjson.CJson/CJSONIsNumber',
                request_serializer=cjson__pb2.CJSONIsNumberRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONIsNumberResponse.FromString,
                _registered_method=True)
        self.CJSONIsString = channel.unary_unary(
                '/cjson.CJson/CJSONIsString',
                request_serializer=cjson__pb2.CJSONIsStringRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONIsStringResponse.FromString,
                _registered_method=True)
        self.CJSONIsArray = channel.unary_unary(
                '/cjson.CJson/CJSONIsArray',
                request_serializer=cjson__pb2.CJSONIsArrayRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONIsArrayResponse.FromString,
                _registered_method=True)
        self.CJSONIsObject = channel.unary_unary(
                '/cjson.CJson/CJSONIsObject',
                request_serializer=cjson__pb2.CJSONIsObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONIsObjectResponse.FromString,
                _registered_method=True)
        self.CJSONIsRaw = channel.unary_unary(
                '/cjson.CJson/CJSONIsRaw',
                request_serializer=cjson__pb2.CJSONIsRawRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONIsRawResponse.FromString,
                _registered_method=True)
        self.CJSONCreateNull = channel.unary_unary(
                '/cjson.CJson/CJSONCreateNull',
                request_serializer=cjson__pb2.CJSONCreateNullRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCreateNullResponse.FromString,
                _registered_method=True)
        self.CJSONCreateTrue = channel.unary_unary(
                '/cjson.CJson/CJSONCreateTrue',
                request_serializer=cjson__pb2.CJSONCreateTrueRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCreateTrueResponse.FromString,
                _registered_method=True)
        self.CJSONCreateFalse = channel.unary_unary(
                '/cjson.CJson/CJSONCreateFalse',
                request_serializer=cjson__pb2.CJSONCreateFalseRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCreateFalseResponse.FromString,
                _registered_method=True)
        self.CJSONCreateBool = channel.unary_unary(
                '/cjson.CJson/CJSONCreateBool',
                request_serializer=cjson__pb2.CJSONCreateBoolRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCreateBoolResponse.FromString,
                _registered_method=True)
        self.CJSONCreateNumber = channel.unary_unary(
                '/cjson.CJson/CJSONCreateNumber',
                request_serializer=cjson__pb2.CJSONCreateNumberRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCreateNumberResponse.FromString,
                _registered_method=True)
        self.CJSONCreateString = channel.unary_unary(
                '/cjson.CJson/CJSONCreateString',
                request_serializer=cjson__pb2.CJSONCreateStringRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCreateStringResponse.FromString,
                _registered_method=True)
        self.CJSONCreateRaw = channel.unary_unary(
                '/cjson.CJson/CJSONCreateRaw',
                request_serializer=cjson__pb2.CJSONCreateRawRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCreateRawResponse.FromString,
                _registered_method=True)
        self.CJSONCreateArray = channel.unary_unary(
                '/cjson.CJson/CJSONCreateArray',
                request_serializer=cjson__pb2.CJSONCreateArrayRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCreateArrayResponse.FromString,
                _registered_method=True)
        self.CJSONCreateObject = channel.unary_unary(
                '/cjson.CJson/CJSONCreateObject',
                request_serializer=cjson__pb2.CJSONCreateObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCreateObjectResponse.FromString,
                _registered_method=True)
        self.CJSONCreateStringReference = channel.unary_unary(
                '/cjson.CJson/CJSONCreateStringReference',
                request_serializer=cjson__pb2.CJSONCreateStringReferenceRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCreateStringReferenceResponse.FromString,
                _registered_method=True)
        self.CJSONCreateObjectReference = channel.unary_unary(
                '/cjson.CJson/CJSONCreateObjectReference',
                request_serializer=cjson__pb2.CJSONCreateObjectReferenceRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCreateObjectReferenceResponse.FromString,
                _registered_method=True)
        self.CJSONCreateArrayReference = channel.unary_unary(
                '/cjson.CJson/CJSONCreateArrayReference',
                request_serializer=cjson__pb2.CJSONCreateArrayReferenceRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCreateArrayReferenceResponse.FromString,
                _registered_method=True)
        self.CJSONAddItemToArray = channel.unary_unary(
                '/cjson.CJson/CJSONAddItemToArray',
                request_serializer=cjson__pb2.CJSONAddItemToArrayRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddItemToArrayResponse.FromString,
                _registered_method=True)
        self.CJSONAddItemToObject = channel.unary_unary(
                '/cjson.CJson/CJSONAddItemToObject',
                request_serializer=cjson__pb2.CJSONAddItemToObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddItemToObjectResponse.FromString,
                _registered_method=True)
        self.CJSONAddItemToObjectCS = channel.unary_unary(
                '/cjson.CJson/CJSONAddItemToObjectCS',
                request_serializer=cjson__pb2.CJSONAddItemToObjectCSRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddItemToObjectCSResponse.FromString,
                _registered_method=True)
        self.CJSONAddItemReferenceToArray = channel.unary_unary(
                '/cjson.CJson/CJSONAddItemReferenceToArray',
                request_serializer=cjson__pb2.CJSONAddItemReferenceToArrayRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddItemReferenceToArrayResponse.FromString,
                _registered_method=True)
        self.CJSONAddItemReferenceToObject = channel.unary_unary(
                '/cjson.CJson/CJSONAddItemReferenceToObject',
                request_serializer=cjson__pb2.CJSONAddItemReferenceToObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddItemReferenceToObjectResponse.FromString,
                _registered_method=True)
        self.CJSONDetachItemViaPointer = channel.unary_unary(
                '/cjson.CJson/CJSONDetachItemViaPointer',
                request_serializer=cjson__pb2.CJSONDetachItemViaPointerRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONDetachItemViaPointerResponse.FromString,
                _registered_method=True)
        self.CJSONDetachItemFromArray = channel.unary_unary(
                '/cjson.CJson/CJSONDetachItemFromArray',
                request_serializer=cjson__pb2.CJSONDetachItemFromArrayRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONDetachItemFromArrayResponse.FromString,
                _registered_method=True)
        self.CJSONDeleteItemFromArray = channel.unary_unary(
                '/cjson.CJson/CJSONDeleteItemFromArray',
                request_serializer=cjson__pb2.CJSONDeleteItemFromArrayRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONDeleteItemFromArrayResponse.FromString,
                _registered_method=True)
        self.CJSONDetachItemFromObject = channel.unary_unary(
                '/cjson.CJson/CJSONDetachItemFromObject',
                request_serializer=cjson__pb2.CJSONDetachItemFromObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONDetachItemFromObjectResponse.FromString,
                _registered_method=True)
        self.CJSONDetachItemFromObjectCaseSensitive = channel.unary_unary(
                '/cjson.CJson/CJSONDetachItemFromObjectCaseSensitive',
                request_serializer=cjson__pb2.CJSONDetachItemFromObjectCaseSensitiveRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONDetachItemFromObjectCaseSensitiveResponse.FromString,
                _registered_method=True)
        self.CJSONDeleteItemFromObject = channel.unary_unary(
                '/cjson.CJson/CJSONDeleteItemFromObject',
                request_serializer=cjson__pb2.CJSONDeleteItemFromObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONDeleteItemFromObjectResponse.FromString,
                _registered_method=True)
        self.CJSONDeleteItemFromObjectCaseSensitive = channel.unary_unary(
                '/cjson.CJson/CJSONDeleteItemFromObjectCaseSensitive',
                request_serializer=cjson__pb2.CJSONDeleteItemFromObjectCaseSensitiveRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONDeleteItemFromObjectCaseSensitiveResponse.FromString,
                _registered_method=True)
        self.CJSONInsertItemInArray = channel.unary_unary(
                '/cjson.CJson/CJSONInsertItemInArray',
                request_serializer=cjson__pb2.CJSONInsertItemInArrayRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONInsertItemInArrayResponse.FromString,
                _registered_method=True)
        self.CJSONReplaceItemViaPointer = channel.unary_unary(
                '/cjson.CJson/CJSONReplaceItemViaPointer',
                request_serializer=cjson__pb2.CJSONReplaceItemViaPointerRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONReplaceItemViaPointerResponse.FromString,
                _registered_method=True)
        self.CJSONReplaceItemInArray = channel.unary_unary(
                '/cjson.CJson/CJSONReplaceItemInArray',
                request_serializer=cjson__pb2.CJSONReplaceItemInArrayRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONReplaceItemInArrayResponse.FromString,
                _registered_method=True)
        self.CJSONReplaceItemInObject = channel.unary_unary(
                '/cjson.CJson/CJSONReplaceItemInObject',
                request_serializer=cjson__pb2.CJSONReplaceItemInObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONReplaceItemInObjectResponse.FromString,
                _registered_method=True)
        self.CJSONReplaceItemInObjectCaseSensitive = channel.unary_unary(
                '/cjson.CJson/CJSONReplaceItemInObjectCaseSensitive',
                request_serializer=cjson__pb2.CJSONReplaceItemInObjectCaseSensitiveRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONReplaceItemInObjectCaseSensitiveResponse.FromString,
                _registered_method=True)
        self.CJSONDuplicate = channel.unary_unary(
                '/cjson.CJson/CJSONDuplicate',
                request_serializer=cjson__pb2.CJSONDuplicateRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONDuplicateResponse.FromString,
                _registered_method=True)
        self.CJSONCompare = channel.unary_unary(
                '/cjson.CJson/CJSONCompare',
                request_serializer=cjson__pb2.CJSONCompareRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONCompareResponse.FromString,
                _registered_method=True)
        self.CJSONAddNullToObject = channel.unary_unary(
                '/cjson.CJson/CJSONAddNullToObject',
                request_serializer=cjson__pb2.CJSONAddNullToObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddNullToObjectResponse.FromString,
                _registered_method=True)
        self.CJSONAddTrueToObject = channel.unary_unary(
                '/cjson.CJson/CJSONAddTrueToObject',
                request_serializer=cjson__pb2.CJSONAddTrueToObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddTrueToObjectResponse.FromString,
                _registered_method=True)
        self.CJSONAddFalseToObject = channel.unary_unary(
                '/cjson.CJson/CJSONAddFalseToObject',
                request_serializer=cjson__pb2.CJSONAddFalseToObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddFalseToObjectResponse.FromString,
                _registered_method=True)
        self.CJSONAddBoolToObject = channel.unary_unary(
                '/cjson.CJson/CJSONAddBoolToObject',
                request_serializer=cjson__pb2.CJSONAddBoolToObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddBoolToObjectResponse.FromString,
                _registered_method=True)
        self.CJSONAddNumberToObject = channel.unary_unary(
                '/cjson.CJson/CJSONAddNumberToObject',
                request_serializer=cjson__pb2.CJSONAddNumberToObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddNumberToObjectResponse.FromString,
                _registered_method=True)
        self.CJSONAddStringToObject = channel.unary_unary(
                '/cjson.CJson/CJSONAddStringToObject',
                request_serializer=cjson__pb2.CJSONAddStringToObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddStringToObjectResponse.FromString,
                _registered_method=True)
        self.CJSONAddRawToObject = channel.unary_unary(
                '/cjson.CJson/CJSONAddRawToObject',
                request_serializer=cjson__pb2.CJSONAddRawToObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddRawToObjectResponse.FromString,
                _registered_method=True)
        self.CJSONAddObjectToObject = channel.unary_unary(
                '/cjson.CJson/CJSONAddObjectToObject',
                request_serializer=cjson__pb2.CJSONAddObjectToObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddObjectToObjectResponse.FromString,
                _registered_method=True)
        self.CJSONAddArrayToObject = channel.unary_unary(
                '/cjson.CJson/CJSONAddArrayToObject',
                request_serializer=cjson__pb2.CJSONAddArrayToObjectRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONAddArrayToObjectResponse.FromString,
                _registered_method=True)
        self.CJSONSetNumberHelper = channel.unary_unary(
                '/cjson.CJson/CJSONSetNumberHelper',
                request_serializer=cjson__pb2.CJSONSetNumberHelperRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONSetNumberHelperResponse.FromString,
                _registered_method=True)
        self.CJSONSetValuestring = channel.unary_unary(
                '/cjson.CJson/CJSONSetValuestring',
                request_serializer=cjson__pb2.CJSONSetValuestringRequest.SerializeToString,
                response_deserializer=cjson__pb2.CJSONSetValuestringResponse.FromString,
                _registered_method=True)


class CJsonServicer:
    """Missing associated documentation comment in .proto file."""

    def OpenSession(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CloseSession(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONVersion(self, request, context):
        """stateless: no session required
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONParse(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONParseWithLength(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONPrint(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONPrintUnformatted(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONPrintBuffered(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONDelete(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONGetArraySize(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONGetArrayItem(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONGetObjectItem(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONGetObjectItemCaseSensitive(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONHasObjectItem(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONGetErrorPtr(self, request, context):
        """stateless: no session required
        """
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONGetStringValue(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONGetNumberValue(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONIsInvalid(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONIsFalse(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONIsTrue(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONIsBool(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONIsNull(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONIsNumber(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONIsString(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONIsArray(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONIsObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONIsRaw(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCreateNull(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCreateTrue(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCreateFalse(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCreateBool(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCreateNumber(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCreateString(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCreateRaw(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCreateArray(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCreateObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCreateStringReference(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCreateObjectReference(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCreateArrayReference(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddItemToArray(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddItemToObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddItemToObjectCS(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddItemReferenceToArray(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddItemReferenceToObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONDetachItemViaPointer(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONDetachItemFromArray(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONDeleteItemFromArray(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONDetachItemFromObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONDetachItemFromObjectCaseSensitive(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONDeleteItemFromObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONDeleteItemFromObjectCaseSensitive(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONInsertItemInArray(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONReplaceItemViaPointer(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONReplaceItemInArray(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONReplaceItemInObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONReplaceItemInObjectCaseSensitive(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONDuplicate(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONCompare(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddNullToObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddTrueToObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddFalseToObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddBoolToObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddNumberToObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddStringToObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddRawToObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddObjectToObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONAddArrayToObject(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONSetNumberHelper(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CJSONSetValuestring(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_CJsonServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'OpenSession': grpc.unary_unary_rpc_method_handler(
                    servicer.OpenSession,
                    request_deserializer=cjson__pb2.OpenSessionRequest.FromString,
                    response_serializer=cjson__pb2.OpenSessionResponse.SerializeToString,
            ),
            'CloseSession': grpc.unary_unary_rpc_method_handler(
                    servicer.CloseSession,
                    request_deserializer=cjson__pb2.CloseSessionRequest.FromString,
                    response_serializer=cjson__pb2.CloseSessionResponse.SerializeToString,
            ),
            'CJSONVersion': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONVersion,
                    request_deserializer=cjson__pb2.CJSONVersionRequest.FromString,
                    response_serializer=cjson__pb2.CJSONVersionResponse.SerializeToString,
            ),
            'CJSONParse': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONParse,
                    request_deserializer=cjson__pb2.CJSONParseRequest.FromString,
                    response_serializer=cjson__pb2.CJSONParseResponse.SerializeToString,
            ),
            'CJSONParseWithLength': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONParseWithLength,
                    request_deserializer=cjson__pb2.CJSONParseWithLengthRequest.FromString,
                    response_serializer=cjson__pb2.CJSONParseWithLengthResponse.SerializeToString,
            ),
            'CJSONPrint': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONPrint,
                    request_deserializer=cjson__pb2.CJSONPrintRequest.FromString,
                    response_serializer=cjson__pb2.CJSONPrintResponse.SerializeToString,
            ),
            'CJSONPrintUnformatted': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONPrintUnformatted,
                    request_deserializer=cjson__pb2.CJSONPrintUnformattedRequest.FromString,
                    response_serializer=cjson__pb2.CJSONPrintUnformattedResponse.SerializeToString,
            ),
            'CJSONPrintBuffered': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONPrintBuffered,
                    request_deserializer=cjson__pb2.CJSONPrintBufferedRequest.FromString,
                    response_serializer=cjson__pb2.CJSONPrintBufferedResponse.SerializeToString,
            ),
            'CJSONDelete': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONDelete,
                    request_deserializer=cjson__pb2.CJSONDeleteRequest.FromString,
                    response_serializer=cjson__pb2.CJSONDeleteResponse.SerializeToString,
            ),
            'CJSONGetArraySize': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONGetArraySize,
                    request_deserializer=cjson__pb2.CJSONGetArraySizeRequest.FromString,
                    response_serializer=cjson__pb2.CJSONGetArraySizeResponse.SerializeToString,
            ),
            'CJSONGetArrayItem': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONGetArrayItem,
                    request_deserializer=cjson__pb2.CJSONGetArrayItemRequest.FromString,
                    response_serializer=cjson__pb2.CJSONGetArrayItemResponse.SerializeToString,
            ),
            'CJSONGetObjectItem': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONGetObjectItem,
                    request_deserializer=cjson__pb2.CJSONGetObjectItemRequest.FromString,
                    response_serializer=cjson__pb2.CJSONGetObjectItemResponse.SerializeToString,
            ),
            'CJSONGetObjectItemCaseSensitive': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONGetObjectItemCaseSensitive,
                    request_deserializer=cjson__pb2.CJSONGetObjectItemCaseSensitiveRequest.FromString,
                    response_serializer=cjson__pb2.CJSONGetObjectItemCaseSensitiveResponse.SerializeToString,
            ),
            'CJSONHasObjectItem': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONHasObjectItem,
                    request_deserializer=cjson__pb2.CJSONHasObjectItemRequest.FromString,
                    response_serializer=cjson__pb2.CJSONHasObjectItemResponse.SerializeToString,
            ),
            'CJSONGetErrorPtr': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONGetErrorPtr,
                    request_deserializer=cjson__pb2.CJSONGetErrorPtrRequest.FromString,
                    response_serializer=cjson__pb2.CJSONGetErrorPtrResponse.SerializeToString,
            ),
            'CJSONGetStringValue': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONGetStringValue,
                    request_deserializer=cjson__pb2.CJSONGetStringValueRequest.FromString,
                    response_serializer=cjson__pb2.CJSONGetStringValueResponse.SerializeToString,
            ),
            'CJSONGetNumberValue': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONGetNumberValue,
                    request_deserializer=cjson__pb2.CJSONGetNumberValueRequest.FromString,
                    response_serializer=cjson__pb2.CJSONGetNumberValueResponse.SerializeToString,
            ),
            'CJSONIsInvalid': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONIsInvalid,
                    request_deserializer=cjson__pb2.CJSONIsInvalidRequest.FromString,
                    response_serializer=cjson__pb2.CJSONIsInvalidResponse.SerializeToString,
            ),
            'CJSONIsFalse': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONIsFalse,
                    request_deserializer=cjson__pb2.CJSONIsFalseRequest.FromString,
                    response_serializer=cjson__pb2.CJSONIsFalseResponse.SerializeToString,
            ),
            'CJSONIsTrue': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONIsTrue,
                    request_deserializer=cjson__pb2.CJSONIsTrueRequest.FromString,
                    response_serializer=cjson__pb2.CJSONIsTrueResponse.SerializeToString,
            ),
            'CJSONIsBool': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONIsBool,
                    request_deserializer=cjson__pb2.CJSONIsBoolRequest.FromString,
                    response_serializer=cjson__pb2.CJSONIsBoolResponse.SerializeToString,
            ),
            'CJSONIsNull': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONIsNull,
                    request_deserializer=cjson__pb2.CJSONIsNullRequest.FromString,
                    response_serializer=cjson__pb2.CJSONIsNullResponse.SerializeToString,
            ),
            'CJSONIsNumber': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONIsNumber,
                    request_deserializer=cjson__pb2.CJSONIsNumberRequest.FromString,
                    response_serializer=cjson__pb2.CJSONIsNumberResponse.SerializeToString,
            ),
            'CJSONIsString': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONIsString,
                    request_deserializer=cjson__pb2.CJSONIsStringRequest.FromString,
                    response_serializer=cjson__pb2.CJSONIsStringResponse.SerializeToString,
            ),
            'CJSONIsArray': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONIsArray,
                    request_deserializer=cjson__pb2.CJSONIsArrayRequest.FromString,
                    response_serializer=cjson__pb2.CJSONIsArrayResponse.SerializeToString,
            ),
            'CJSONIsObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONIsObject,
                    request_deserializer=cjson__pb2.CJSONIsObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONIsObjectResponse.SerializeToString,
            ),
            'CJSONIsRaw': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONIsRaw,
                    request_deserializer=cjson__pb2.CJSONIsRawRequest.FromString,
                    response_serializer=cjson__pb2.CJSONIsRawResponse.SerializeToString,
            ),
            'CJSONCreateNull': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCreateNull,
                    request_deserializer=cjson__pb2.CJSONCreateNullRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCreateNullResponse.SerializeToString,
            ),
            'CJSONCreateTrue': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCreateTrue,
                    request_deserializer=cjson__pb2.CJSONCreateTrueRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCreateTrueResponse.SerializeToString,
            ),
            'CJSONCreateFalse': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCreateFalse,
                    request_deserializer=cjson__pb2.CJSONCreateFalseRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCreateFalseResponse.SerializeToString,
            ),
            'CJSONCreateBool': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCreateBool,
                    request_deserializer=cjson__pb2.CJSONCreateBoolRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCreateBoolResponse.SerializeToString,
            ),
            'CJSONCreateNumber': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCreateNumber,
                    request_deserializer=cjson__pb2.CJSONCreateNumberRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCreateNumberResponse.SerializeToString,
            ),
            'CJSONCreateString': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCreateString,
                    request_deserializer=cjson__pb2.CJSONCreateStringRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCreateStringResponse.SerializeToString,
            ),
            'CJSONCreateRaw': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCreateRaw,
                    request_deserializer=cjson__pb2.CJSONCreateRawRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCreateRawResponse.SerializeToString,
            ),
            'CJSONCreateArray': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCreateArray,
                    request_deserializer=cjson__pb2.CJSONCreateArrayRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCreateArrayResponse.SerializeToString,
            ),
            'CJSONCreateObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCreateObject,
                    request_deserializer=cjson__pb2.CJSONCreateObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCreateObjectResponse.SerializeToString,
            ),
            'CJSONCreateStringReference': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCreateStringReference,
                    request_deserializer=cjson__pb2.CJSONCreateStringReferenceRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCreateStringReferenceResponse.SerializeToString,
            ),
            'CJSONCreateObjectReference': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCreateObjectReference,
                    request_deserializer=cjson__pb2.CJSONCreateObjectReferenceRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCreateObjectReferenceResponse.SerializeToString,
            ),
            'CJSONCreateArrayReference': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCreateArrayReference,
                    request_deserializer=cjson__pb2.CJSONCreateArrayReferenceRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCreateArrayReferenceResponse.SerializeToString,
            ),
            'CJSONAddItemToArray': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddItemToArray,
                    request_deserializer=cjson__pb2.CJSONAddItemToArrayRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddItemToArrayResponse.SerializeToString,
            ),
            'CJSONAddItemToObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddItemToObject,
                    request_deserializer=cjson__pb2.CJSONAddItemToObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddItemToObjectResponse.SerializeToString,
            ),
            'CJSONAddItemToObjectCS': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddItemToObjectCS,
                    request_deserializer=cjson__pb2.CJSONAddItemToObjectCSRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddItemToObjectCSResponse.SerializeToString,
            ),
            'CJSONAddItemReferenceToArray': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddItemReferenceToArray,
                    request_deserializer=cjson__pb2.CJSONAddItemReferenceToArrayRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddItemReferenceToArrayResponse.SerializeToString,
            ),
            'CJSONAddItemReferenceToObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddItemReferenceToObject,
                    request_deserializer=cjson__pb2.CJSONAddItemReferenceToObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddItemReferenceToObjectResponse.SerializeToString,
            ),
            'CJSONDetachItemViaPointer': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONDetachItemViaPointer,
                    request_deserializer=cjson__pb2.CJSONDetachItemViaPointerRequest.FromString,
                    response_serializer=cjson__pb2.CJSONDetachItemViaPointerResponse.SerializeToString,
            ),
            'CJSONDetachItemFromArray': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONDetachItemFromArray,
                    request_deserializer=cjson__pb2.CJSONDetachItemFromArrayRequest.FromString,
                    response_serializer=cjson__pb2.CJSONDetachItemFromArrayResponse.SerializeToString,
            ),
            'CJSONDeleteItemFromArray': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONDeleteItemFromArray,
                    request_deserializer=cjson__pb2.CJSONDeleteItemFromArrayRequest.FromString,
                    response_serializer=cjson__pb2.CJSONDeleteItemFromArrayResponse.SerializeToString,
            ),
            'CJSONDetachItemFromObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONDetachItemFromObject,
                    request_deserializer=cjson__pb2.CJSONDetachItemFromObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONDetachItemFromObjectResponse.SerializeToString,
            ),
            'CJSONDetachItemFromObjectCaseSensitive': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONDetachItemFromObjectCaseSensitive,
                    request_deserializer=cjson__pb2.CJSONDetachItemFromObjectCaseSensitiveRequest.FromString,
                    response_serializer=cjson__pb2.CJSONDetachItemFromObjectCaseSensitiveResponse.SerializeToString,
            ),
            'CJSONDeleteItemFromObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONDeleteItemFromObject,
                    request_deserializer=cjson__pb2.CJSONDeleteItemFromObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONDeleteItemFromObjectResponse.SerializeToString,
            ),
            'CJSONDeleteItemFromObjectCaseSensitive': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONDeleteItemFromObjectCaseSensitive,
                    request_deserializer=cjson__pb2.CJSONDeleteItemFromObjectCaseSensitiveRequest.FromString,
                    response_serializer=cjson__pb2.CJSONDeleteItemFromObjectCaseSensitiveResponse.SerializeToString,
            ),
            'CJSONInsertItemInArray': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONInsertItemInArray,
                    request_deserializer=cjson__pb2.CJSONInsertItemInArrayRequest.FromString,
                    response_serializer=cjson__pb2.CJSONInsertItemInArrayResponse.SerializeToString,
            ),
            'CJSONReplaceItemViaPointer': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONReplaceItemViaPointer,
                    request_deserializer=cjson__pb2.CJSONReplaceItemViaPointerRequest.FromString,
                    response_serializer=cjson__pb2.CJSONReplaceItemViaPointerResponse.SerializeToString,
            ),
            'CJSONReplaceItemInArray': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONReplaceItemInArray,
                    request_deserializer=cjson__pb2.CJSONReplaceItemInArrayRequest.FromString,
                    response_serializer=cjson__pb2.CJSONReplaceItemInArrayResponse.SerializeToString,
            ),
            'CJSONReplaceItemInObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONReplaceItemInObject,
                    request_deserializer=cjson__pb2.CJSONReplaceItemInObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONReplaceItemInObjectResponse.SerializeToString,
            ),
            'CJSONReplaceItemInObjectCaseSensitive': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONReplaceItemInObjectCaseSensitive,
                    request_deserializer=cjson__pb2.CJSONReplaceItemInObjectCaseSensitiveRequest.FromString,
                    response_serializer=cjson__pb2.CJSONReplaceItemInObjectCaseSensitiveResponse.SerializeToString,
            ),
            'CJSONDuplicate': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONDuplicate,
                    request_deserializer=cjson__pb2.CJSONDuplicateRequest.FromString,
                    response_serializer=cjson__pb2.CJSONDuplicateResponse.SerializeToString,
            ),
            'CJSONCompare': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONCompare,
                    request_deserializer=cjson__pb2.CJSONCompareRequest.FromString,
                    response_serializer=cjson__pb2.CJSONCompareResponse.SerializeToString,
            ),
            'CJSONAddNullToObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddNullToObject,
                    request_deserializer=cjson__pb2.CJSONAddNullToObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddNullToObjectResponse.SerializeToString,
            ),
            'CJSONAddTrueToObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddTrueToObject,
                    request_deserializer=cjson__pb2.CJSONAddTrueToObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddTrueToObjectResponse.SerializeToString,
            ),
            'CJSONAddFalseToObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddFalseToObject,
                    request_deserializer=cjson__pb2.CJSONAddFalseToObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddFalseToObjectResponse.SerializeToString,
            ),
            'CJSONAddBoolToObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddBoolToObject,
                    request_deserializer=cjson__pb2.CJSONAddBoolToObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddBoolToObjectResponse.SerializeToString,
            ),
            'CJSONAddNumberToObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddNumberToObject,
                    request_deserializer=cjson__pb2.CJSONAddNumberToObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddNumberToObjectResponse.SerializeToString,
            ),
            'CJSONAddStringToObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddStringToObject,
                    request_deserializer=cjson__pb2.CJSONAddStringToObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddStringToObjectResponse.SerializeToString,
            ),
            'CJSONAddRawToObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddRawToObject,
                    request_deserializer=cjson__pb2.CJSONAddRawToObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddRawToObjectResponse.SerializeToString,
            ),
            'CJSONAddObjectToObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddObjectToObject,
                    request_deserializer=cjson__pb2.CJSONAddObjectToObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddObjectToObjectResponse.SerializeToString,
            ),
            'CJSONAddArrayToObject': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONAddArrayToObject,
                    request_deserializer=cjson__pb2.CJSONAddArrayToObjectRequest.FromString,
                    response_serializer=cjson__pb2.CJSONAddArrayToObjectResponse.SerializeToString,
            ),
            'CJSONSetNumberHelper': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONSetNumberHelper,
                    request_deserializer=cjson__pb2.CJSONSetNumberHelperRequest.FromString,
                    response_serializer=cjson__pb2.CJSONSetNumberHelperResponse.SerializeToString,
            ),
            'CJSONSetValuestring': grpc.unary_unary_rpc_method_handler(
                    servicer.CJSONSetValuestring,
                    request_deserializer=cjson__pb2.CJSONSetValuestringRequest.FromString,
                    response_serializer=cjson__pb2.CJSONSetValuestringResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'cjson.CJson', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('cjson.CJson', rpc_method_handlers)


                                             
class CJson:
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def OpenSession(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/OpenSession',
            cjson__pb2.OpenSessionRequest.SerializeToString,
            cjson__pb2.OpenSessionResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CloseSession(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CloseSession',
            cjson__pb2.CloseSessionRequest.SerializeToString,
            cjson__pb2.CloseSessionResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONVersion(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONVersion',
            cjson__pb2.CJSONVersionRequest.SerializeToString,
            cjson__pb2.CJSONVersionResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONParse(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONParse',
            cjson__pb2.CJSONParseRequest.SerializeToString,
            cjson__pb2.CJSONParseResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONParseWithLength(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONParseWithLength',
            cjson__pb2.CJSONParseWithLengthRequest.SerializeToString,
            cjson__pb2.CJSONParseWithLengthResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONPrint(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONPrint',
            cjson__pb2.CJSONPrintRequest.SerializeToString,
            cjson__pb2.CJSONPrintResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONPrintUnformatted(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONPrintUnformatted',
            cjson__pb2.CJSONPrintUnformattedRequest.SerializeToString,
            cjson__pb2.CJSONPrintUnformattedResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONPrintBuffered(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONPrintBuffered',
            cjson__pb2.CJSONPrintBufferedRequest.SerializeToString,
            cjson__pb2.CJSONPrintBufferedResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONDelete(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONDelete',
            cjson__pb2.CJSONDeleteRequest.SerializeToString,
            cjson__pb2.CJSONDeleteResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONGetArraySize(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONGetArraySize',
            cjson__pb2.CJSONGetArraySizeRequest.SerializeToString,
            cjson__pb2.CJSONGetArraySizeResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONGetArrayItem(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONGetArrayItem',
            cjson__pb2.CJSONGetArrayItemRequest.SerializeToString,
            cjson__pb2.CJSONGetArrayItemResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONGetObjectItem(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONGetObjectItem',
            cjson__pb2.CJSONGetObjectItemRequest.SerializeToString,
            cjson__pb2.CJSONGetObjectItemResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONGetObjectItemCaseSensitive(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONGetObjectItemCaseSensitive',
            cjson__pb2.CJSONGetObjectItemCaseSensitiveRequest.SerializeToString,
            cjson__pb2.CJSONGetObjectItemCaseSensitiveResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONHasObjectItem(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONHasObjectItem',
            cjson__pb2.CJSONHasObjectItemRequest.SerializeToString,
            cjson__pb2.CJSONHasObjectItemResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONGetErrorPtr(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONGetErrorPtr',
            cjson__pb2.CJSONGetErrorPtrRequest.SerializeToString,
            cjson__pb2.CJSONGetErrorPtrResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONGetStringValue(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONGetStringValue',
            cjson__pb2.CJSONGetStringValueRequest.SerializeToString,
            cjson__pb2.CJSONGetStringValueResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONGetNumberValue(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONGetNumberValue',
            cjson__pb2.CJSONGetNumberValueRequest.SerializeToString,
            cjson__pb2.CJSONGetNumberValueResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONIsInvalid(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONIsInvalid',
            cjson__pb2.CJSONIsInvalidRequest.SerializeToString,
            cjson__pb2.CJSONIsInvalidResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONIsFalse(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONIsFalse',
            cjson__pb2.CJSONIsFalseRequest.SerializeToString,
            cjson__pb2.CJSONIsFalseResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONIsTrue(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONIsTrue',
            cjson__pb2.CJSONIsTrueRequest.SerializeToString,
            cjson__pb2.CJSONIsTrueResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONIsBool(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONIsBool',
            cjson__pb2.CJSONIsBoolRequest.SerializeToString,
            cjson__pb2.CJSONIsBoolResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONIsNull(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONIsNull',
            cjson__pb2.CJSONIsNullRequest.SerializeToString,
            cjson__pb2.CJSONIsNullResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONIsNumber(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONIsNumber',
            cjson__pb2.CJSONIsNumberRequest.SerializeToString,
            cjson__pb2.CJSONIsNumberResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONIsString(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONIsString',
            cjson__pb2.CJSONIsStringRequest.SerializeToString,
            cjson__pb2.CJSONIsStringResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONIsArray(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONIsArray',
            cjson__pb2.CJSONIsArrayRequest.SerializeToString,
            cjson__pb2.CJSONIsArrayResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONIsObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONIsObject',
            cjson__pb2.CJSONIsObjectRequest.SerializeToString,
            cjson__pb2.CJSONIsObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONIsRaw(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONIsRaw',
            cjson__pb2.CJSONIsRawRequest.SerializeToString,
            cjson__pb2.CJSONIsRawResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCreateNull(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCreateNull',
            cjson__pb2.CJSONCreateNullRequest.SerializeToString,
            cjson__pb2.CJSONCreateNullResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCreateTrue(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCreateTrue',
            cjson__pb2.CJSONCreateTrueRequest.SerializeToString,
            cjson__pb2.CJSONCreateTrueResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCreateFalse(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCreateFalse',
            cjson__pb2.CJSONCreateFalseRequest.SerializeToString,
            cjson__pb2.CJSONCreateFalseResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCreateBool(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCreateBool',
            cjson__pb2.CJSONCreateBoolRequest.SerializeToString,
            cjson__pb2.CJSONCreateBoolResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCreateNumber(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCreateNumber',
            cjson__pb2.CJSONCreateNumberRequest.SerializeToString,
            cjson__pb2.CJSONCreateNumberResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCreateString(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCreateString',
            cjson__pb2.CJSONCreateStringRequest.SerializeToString,
            cjson__pb2.CJSONCreateStringResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCreateRaw(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCreateRaw',
            cjson__pb2.CJSONCreateRawRequest.SerializeToString,
            cjson__pb2.CJSONCreateRawResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCreateArray(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCreateArray',
            cjson__pb2.CJSONCreateArrayRequest.SerializeToString,
            cjson__pb2.CJSONCreateArrayResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCreateObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCreateObject',
            cjson__pb2.CJSONCreateObjectRequest.SerializeToString,
            cjson__pb2.CJSONCreateObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCreateStringReference(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCreateStringReference',
            cjson__pb2.CJSONCreateStringReferenceRequest.SerializeToString,
            cjson__pb2.CJSONCreateStringReferenceResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCreateObjectReference(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCreateObjectReference',
            cjson__pb2.CJSONCreateObjectReferenceRequest.SerializeToString,
            cjson__pb2.CJSONCreateObjectReferenceResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCreateArrayReference(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCreateArrayReference',
            cjson__pb2.CJSONCreateArrayReferenceRequest.SerializeToString,
            cjson__pb2.CJSONCreateArrayReferenceResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddItemToArray(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddItemToArray',
            cjson__pb2.CJSONAddItemToArrayRequest.SerializeToString,
            cjson__pb2.CJSONAddItemToArrayResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddItemToObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddItemToObject',
            cjson__pb2.CJSONAddItemToObjectRequest.SerializeToString,
            cjson__pb2.CJSONAddItemToObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddItemToObjectCS(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddItemToObjectCS',
            cjson__pb2.CJSONAddItemToObjectCSRequest.SerializeToString,
            cjson__pb2.CJSONAddItemToObjectCSResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddItemReferenceToArray(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddItemReferenceToArray',
            cjson__pb2.CJSONAddItemReferenceToArrayRequest.SerializeToString,
            cjson__pb2.CJSONAddItemReferenceToArrayResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddItemReferenceToObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddItemReferenceToObject',
            cjson__pb2.CJSONAddItemReferenceToObjectRequest.SerializeToString,
            cjson__pb2.CJSONAddItemReferenceToObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONDetachItemViaPointer(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONDetachItemViaPointer',
            cjson__pb2.CJSONDetachItemViaPointerRequest.SerializeToString,
            cjson__pb2.CJSONDetachItemViaPointerResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONDetachItemFromArray(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONDetachItemFromArray',
            cjson__pb2.CJSONDetachItemFromArrayRequest.SerializeToString,
            cjson__pb2.CJSONDetachItemFromArrayResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONDeleteItemFromArray(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONDeleteItemFromArray',
            cjson__pb2.CJSONDeleteItemFromArrayRequest.SerializeToString,
            cjson__pb2.CJSONDeleteItemFromArrayResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONDetachItemFromObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONDetachItemFromObject',
            cjson__pb2.CJSONDetachItemFromObjectRequest.SerializeToString,
            cjson__pb2.CJSONDetachItemFromObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONDetachItemFromObjectCaseSensitive(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONDetachItemFromObjectCaseSensitive',
            cjson__pb2.CJSONDetachItemFromObjectCaseSensitiveRequest.SerializeToString,
            cjson__pb2.CJSONDetachItemFromObjectCaseSensitiveResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONDeleteItemFromObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONDeleteItemFromObject',
            cjson__pb2.CJSONDeleteItemFromObjectRequest.SerializeToString,
            cjson__pb2.CJSONDeleteItemFromObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONDeleteItemFromObjectCaseSensitive(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONDeleteItemFromObjectCaseSensitive',
            cjson__pb2.CJSONDeleteItemFromObjectCaseSensitiveRequest.SerializeToString,
            cjson__pb2.CJSONDeleteItemFromObjectCaseSensitiveResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONInsertItemInArray(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONInsertItemInArray',
            cjson__pb2.CJSONInsertItemInArrayRequest.SerializeToString,
            cjson__pb2.CJSONInsertItemInArrayResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONReplaceItemViaPointer(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONReplaceItemViaPointer',
            cjson__pb2.CJSONReplaceItemViaPointerRequest.SerializeToString,
            cjson__pb2.CJSONReplaceItemViaPointerResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONReplaceItemInArray(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONReplaceItemInArray',
            cjson__pb2.CJSONReplaceItemInArrayRequest.SerializeToString,
            cjson__pb2.CJSONReplaceItemInArrayResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONReplaceItemInObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONReplaceItemInObject',
            cjson__pb2.CJSONReplaceItemInObjectRequest.SerializeToString,
            cjson__pb2.CJSONReplaceItemInObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONReplaceItemInObjectCaseSensitive(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONReplaceItemInObjectCaseSensitive',
            cjson__pb2.CJSONReplaceItemInObjectCaseSensitiveRequest.SerializeToString,
            cjson__pb2.CJSONReplaceItemInObjectCaseSensitiveResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONDuplicate(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONDuplicate',
            cjson__pb2.CJSONDuplicateRequest.SerializeToString,
            cjson__pb2.CJSONDuplicateResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONCompare(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONCompare',
            cjson__pb2.CJSONCompareRequest.SerializeToString,
            cjson__pb2.CJSONCompareResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddNullToObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddNullToObject',
            cjson__pb2.CJSONAddNullToObjectRequest.SerializeToString,
            cjson__pb2.CJSONAddNullToObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddTrueToObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddTrueToObject',
            cjson__pb2.CJSONAddTrueToObjectRequest.SerializeToString,
            cjson__pb2.CJSONAddTrueToObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddFalseToObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddFalseToObject',
            cjson__pb2.CJSONAddFalseToObjectRequest.SerializeToString,
            cjson__pb2.CJSONAddFalseToObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddBoolToObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddBoolToObject',
            cjson__pb2.CJSONAddBoolToObjectRequest.SerializeToString,
            cjson__pb2.CJSONAddBoolToObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddNumberToObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddNumberToObject',
            cjson__pb2.CJSONAddNumberToObjectRequest.SerializeToString,
            cjson__pb2.CJSONAddNumberToObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddStringToObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddStringToObject',
            cjson__pb2.CJSONAddStringToObjectRequest.SerializeToString,
            cjson__pb2.CJSONAddStringToObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddRawToObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddRawToObject',
            cjson__pb2.CJSONAddRawToObjectRequest.SerializeToString,
            cjson__pb2.CJSONAddRawToObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddObjectToObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddObjectToObject',
            cjson__pb2.CJSONAddObjectToObjectRequest.SerializeToString,
            cjson__pb2.CJSONAddObjectToObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONAddArrayToObject(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONAddArrayToObject',
            cjson__pb2.CJSONAddArrayToObjectRequest.SerializeToString,
            cjson__pb2.CJSONAddArrayToObjectResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONSetNumberHelper(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONSetNumberHelper',
            cjson__pb2.CJSONSetNumberHelperRequest.SerializeToString,
            cjson__pb2.CJSONSetNumberHelperResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def CJSONSetValuestring(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/cjson.CJson/CJSONSetValuestring',
            cjson__pb2.CJSONSetValuestringRequest.SerializeToString,
            cjson__pb2.CJSONSetValuestringResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)
