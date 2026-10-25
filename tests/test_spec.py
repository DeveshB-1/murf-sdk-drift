from murf_drift import spec


def test_norm_path_ignores_param_names_and_leading_slash():
    assert spec.norm_path("/v1/speech/voices/cloned/{voiceId}") == spec.norm_path("v1/speech/voices/cloned/{}")
    assert spec.norm_path("v1/x/") == "/v1/x"


def test_rest_operations_flattens_allof_and_drops_auth_header(fix):
    ops = {o.key: o for o in spec.rest_operations(spec.load(str(fix / "openapi.json")))}
    stream = ops[("POST", "/v1/speech/stream")]
    assert stream.body == {"text", "voiceId", "rate", "volumeOffset"}
    assert stream.required == {"text", "voiceId"}
    assert stream.headers == {"token"}  # api-key belongs to the client wrapper
    assert ops[("GET", "/v1/speech/voices")].query == {"model"}
    assert ops[("POST", "/v1/speech/voices/create")].body == {"file", "name"}


def test_ws_channels_unpack_oneof_members_and_query(fix):
    channels, r = spec.ws_channels(spec.load(str(fix / "asyncapi.json")))
    by = {c.name: c for c in channels}
    assert [m.name for m in by["/stream-input"].messages] == ["wordTimestamp", "errorOutput", "sendText"]
    assert by["/stream-input"].query == {"model", "sample_rate"}
    send = next(m for m in by["/stream-input"].messages if m.name == "sendText")
    fields = r.object_fields(send.schema)
    # nullable anyOf around a $ref resolves to the referenced object
    assert set(r.object_fields(fields["voice_config"])) == {"voice_id", "volumeOffset"}


def test_object_fields_reads_map_values():
    r = spec.Resolver({"components": {"schemas": {"P": {"type": "object", "properties": {"type": {}, "pronunciation": {}}}}}})
    schema = {"type": "object", "additionalProperties": {"$ref": "#/components/schemas/P"}}
    assert set(r.object_fields(schema)) == {"type", "pronunciation"}
