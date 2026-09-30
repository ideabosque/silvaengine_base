"""Handler._get_metadata 数据域 claims 白名单提升回归测试。

回归锁定（2026-09-30 隔离未生效根因修复）：``_get_metadata`` 的 claims
白名单曾漏提 ``tenant_id``/``merchant_id``，导致 PermAuthorizer 注入的
数据域 claims 被 Gateway 闸口丢弃，引擎侧 ``_get_ctx_tenant_id`` 运行时
恒为 None，全部引擎数据域过滤 fail-open 泄漏全量数据。

三个用例：
1. authorizer 含 claims → metadata 提升 tenant_id/merchant_id/user_id；
2. 显式 None claims（平台级数据域）→ 键存在且值为 None 透传；
3. 无 authorizer 且无 JWT → metadata 不含 claims 键（fail-closed 形态）。
"""

import logging

import pytest

from silvaengine_base.handler import Handler

EVENT_BASE = {
    "headers": {},
    "pathParameters": {"area": "core", "endpoint_id": "testendpoint"},
    "queryStringParameters": {},
    "requestContext": {"stage": "beta"},
}


def _make_handler(event):
    return Handler(
        event=event,
        context=None,
        setting={},
        logger=logging.getLogger("test_handler_metadata"),
    )


class TestMetadataClaimPromotion:
    """_get_metadata 白名单提升 tenant_id/merchant_id claims。"""

    def test_authorizer_claims_promoted_to_metadata(self):
        """authorizer 含数据域 claims → metadata 含 tenant_id/merchant_id。"""
        event = {
            **EVENT_BASE,
            "requestContext": {
                "stage": "beta",
                "authorizer": {
                    "user_id": "91af1be6-0000-0000-0000-000000000001",
                    "tenant_id": "38638e92-0000-0000-0000-000000000002",
                    "merchant_id": "76fc6397-0000-0000-0000-000000000003",
                    "roles": [{"role_id": "r1", "name": "platform:tenant_admin"}],
                },
            },
        }

        metadata = _make_handler(event)._get_metadata()

        assert metadata["user_id"] == event["requestContext"]["authorizer"][
            "user_id"
        ]
        assert metadata["tenant_id"] == event["requestContext"]["authorizer"][
            "tenant_id"
        ]
        assert metadata["merchant_id"] == event["requestContext"]["authorizer"][
            "merchant_id"
        ]

    def test_explicit_none_claims_pass_through(self):
        """平台级数据域：显式 None claims 按键存在性透传 None 值。

        PermAuthorizer 对系统管理员注入 tenant_id=None / merchant_id=None
        （authorizer.py L195-233），键必须存在以区分「无 claims」与
        「平台级数据域」两种形态。
        """
        event = {
            **EVENT_BASE,
            "requestContext": {
                "stage": "beta",
                "authorizer": {
                    "user_id": "super-admin-1",
                    "tenant_id": None,
                    "merchant_id": None,
                },
            },
        }

        metadata = _make_handler(event)._get_metadata()

        assert "tenant_id" in metadata
        assert metadata["tenant_id"] is None
        assert "merchant_id" in metadata
        assert metadata["merchant_id"] is None

    def test_no_authorizer_and_no_jwt_leaves_no_claim_keys(self):
        """无 authorizer 且无 Authorization header → metadata 无 claims 键。

        兜底 JWT 解析（_parse_token_claims）无 token 可解析返回空 dict，
        白名单循环空转，metadata 不含任何 claims 键。
        """
        metadata = _make_handler(dict(EVENT_BASE))._get_metadata()

        assert "tenant_id" not in metadata
        assert "merchant_id" not in metadata
        assert "user_id" not in metadata
        # 结构性键仍在，证明 metadata 构建链路本身健康
        assert "endpoint_id" in metadata
        assert metadata["endpoint_id"] == "testendpoint"


class TestMetadataJwtFallbackPromotion:
    """JWT 兜底路径（未配置 Lambda authorizer）同样提升 claims。"""

    def test_jwt_claims_promoted_via_fallback(self):
        """Authorization header JWT 的 unverified claims 被提升。

        覆盖 auth_required=False 场景：_get_authorized_user 回落解析 JWT，
        白名单须同样适用于该路径的 claims 键。
        """
        # eyJ0IjoxfQ 无 signature 段落要求（count('.')==2 校验）——
        # 构造 header.payload.sig 三段式：{"tenant_id": "t-1",
        # "merchant_id": "m-1", "sub": "u-9"}
        import base64
        import json

        payload = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "tenant_id": "t-1",
                    "merchant_id": "m-1",
                    "sub": "u-9",
                }
            ).encode("utf-8")
        ).decode("utf-8").rstrip("=")
        token = f"eyJhbGciOiJIUzI1NiJ9.{payload}.sig"

        event = {
            **EVENT_BASE,
            "headers": {"Authorization": f"Bearer {token}"},
        }

        metadata = _make_handler(event)._get_metadata()

        assert metadata["user_id"] == "u-9"
        assert metadata["tenant_id"] == "t-1"
        assert metadata["merchant_id"] == "m-1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])