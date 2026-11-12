"""Regenerate the LedgerLens MCP Excalidraw diagrams. Usage: uv run python docs/diagrams/generate_excalidraw.py docs/diagrams"""

import itertools
import json
import sys
from pathlib import Path

# Tier palette (fill, stroke) — consistent across every diagram
TIER = {
    "client": ("#a5d8ff", "#1971c2"),
    "edge": ("#ffd8a8", "#e8590c"),
    "compute": ("#d0bfff", "#6741d9"),
    "data": ("#c3fae8", "#0c8599"),
    "async": ("#fff3bf", "#e67700"),
    "obs": ("#b2f2bb", "#2f9e44"),
    "security": ("#ffc9c9", "#c92a2a"),
    "external": ("#e9ecef", "#495057"),
    "note": ("#fff9db", "#868e96"),
}
INK = "#1e1e1e"


class Diagram:
    def __init__(self):
        self.els = []
        self.by_id = {}
        self._seed = 1000

    def _base(self, **kw):
        self._seed += 7
        el = {
            "seed": self._seed,
            "version": 1,
            "versionNonce": self._seed * 3,
            "isDeleted": False,
            "angle": 0,
            "opacity": 100,
            "groupIds": [],
            "roughness": 1,
            "strokeWidth": 2,
            "fillStyle": "solid",
            "strokeStyle": "solid",
            "frameId": None,
            "locked": False,
            "link": None,
        }
        el.update(kw)
        self.els.append(el)
        self.by_id[el["id"]] = el
        return el

    def zone(self, id, x, y, w, h, title, tier, title_size=20, title_dx=16):
        fill, stroke = TIER[tier]
        self._base(
            type="rectangle",
            id=id,
            x=x,
            y=y,
            width=w,
            height=h,
            strokeColor=stroke,
            backgroundColor=fill,
            opacity=35,
            strokeStyle="dashed",
            roundness={"type": 3},
            boundElements=[],
        )
        self.text(f"{id}_t", x + title_dx, y + 10, title, size=title_size, color=stroke)

    def box(self, id, x, y, w, h, label, tier, shape="rectangle", size=16, stroke_style="solid"):
        fill, stroke = TIER[tier]
        kw = {
            "type": shape,
            "id": id,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "strokeColor": stroke,
            "backgroundColor": fill,
            "strokeStyle": stroke_style,
            "boundElements": [{"id": f"{id}_t", "type": "text"}],
        }
        if shape == "rectangle":
            kw["roundness"] = {"type": 3}
        self._base(**kw)
        lines = label.split("\n")
        th = len(lines) * size * 1.25
        tw = max(len(l) for l in lines) * size * 0.55
        self._base(
            type="text",
            id=f"{id}_t",
            x=x + (w - tw) / 2,
            y=y + (h - th) / 2,
            width=tw,
            height=th,
            text=label,
            originalText=label,
            fontSize=size,
            fontFamily=1,
            strokeColor=INK,
            backgroundColor="transparent",
            textAlign="center",
            verticalAlign="middle",
            containerId=id,
            autoResize=True,
            lineHeight=1.25,
            boundElements=[],
        )

    def text(self, id, x, y, s, size=16, color=INK):
        lines = s.split("\n")
        self._base(
            type="text",
            id=id,
            x=x,
            y=y,
            width=max(len(l) for l in lines) * size * 0.55,
            height=len(lines) * size * 1.25,
            text=s,
            originalText=s,
            fontSize=size,
            fontFamily=1,
            strokeColor=color,
            backgroundColor="transparent",
            textAlign="left",
            verticalAlign="top",
            containerId=None,
            autoResize=True,
            lineHeight=1.25,
            boundElements=[],
        )

    def title(self, s, sub, x=40, y=20):
        self.text("title", x, y, s, size=32)
        self.text("subtitle", x, y + 46, sub, size=16, color="#495057")

    def _anchor(self, el, fp):
        return el["x"] + el["width"] * fp[0], el["y"] + el["height"] * fp[1]

    def arrow(
        self,
        id,
        src,
        sfp,
        dst,
        dfp,
        label=None,
        via=(),
        color=INK,
        dashed=False,
        size=16,
        start_head=None,
    ):
        s, d = self.by_id[src], self.by_id[dst]
        sx, sy = self._anchor(s, sfp)
        ex, ey = self._anchor(d, dfp)
        pts_abs = [(sx, sy), *via, (ex, ey)]
        pts = [[px - sx, py - sy] for px, py in pts_abs]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        bound = [{"id": f"{id}_t", "type": "text"}] if label else []
        self._base(
            type="arrow",
            id=id,
            x=sx,
            y=sy,
            width=max(xs) - min(xs),
            height=max(ys) - min(ys),
            points=pts,
            strokeColor=color,
            backgroundColor="transparent",
            strokeStyle="dashed" if dashed else "solid",
            roundness={"type": 2},
            startArrowhead=start_head,
            endArrowhead="arrow",
            lastCommittedPoint=None,
            elbowed=False,
            startBinding={"elementId": src, "fixedPoint": list(sfp), "focus": 0, "gap": 4},
            endBinding={"elementId": dst, "fixedPoint": list(dfp), "focus": 0, "gap": 4},
            boundElements=bound,
        )
        for el in {s["id"]: s, d["id"]: d}.values():
            el.setdefault("boundElements", []).append({"id": id, "type": "arrow"})
        if label:
            # midpoint of the longest segment
            segs = list(itertools.pairwise(pts_abs))
            (ax, ay), (bx, by) = max(
                segs, key=lambda p: abs(p[1][0] - p[0][0]) + abs(p[1][1] - p[0][1])
            )
            lines = label.split("\n")
            tw = max(len(l) for l in lines) * size * 0.55
            th = len(lines) * size * 1.25
            self._base(
                type="text",
                id=f"{id}_t",
                x=(ax + bx) / 2 - tw / 2,
                y=(ay + by) / 2 - th / 2,
                width=tw,
                height=th,
                text=label,
                originalText=label,
                fontSize=size,
                fontFamily=1,
                strokeColor=color if color != INK else "#343a40",
                backgroundColor="transparent",
                textAlign="center",
                verticalAlign="middle",
                containerId=id,
                autoResize=True,
                lineHeight=1.25,
                boundElements=[],
            )

    def legend(self, x, y, tiers):
        self.text("legend_h", x, y, "Legend", size=20)
        cx = x
        for tier, name in tiers:
            fill, stroke = TIER[tier]
            self._base(
                type="rectangle",
                id=f"lg_{tier}",
                x=cx,
                y=y + 34,
                width=28,
                height=22,
                strokeColor=stroke,
                backgroundColor=fill,
                roundness={"type": 3},
                boundElements=[],
            )
            self.text(f"lg_{tier}_t", cx + 36, y + 34, name, size=16)
            cx += 36 + len(name) * 16 * 0.55 + 40

    def save(self, path):
        doc = {
            "type": "excalidraw",
            "version": 2,
            "source": "ledgerlens-mcp",
            "elements": self.els,
            "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20},
            "files": {},
        }
        # LF on every OS so regenerated files are byte-identical across machines.
        Path(path).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")


ALL_TIERS = [
    ("client", "Clients"),
    ("edge", "Edge"),
    ("compute", "Compute"),
    ("data", "Data"),
    ("async", "Async"),
    ("obs", "Observability / deploy"),
    ("security", "Security"),
    ("external", "External"),
]


def system_architecture():
    d = Diagram()
    d.title(
        "LedgerLens MCP — AWS deployment (eu-north-1)",
        "Kosha Financial · Lambda container images · RDS PostgreSQL + pgvector · scale-to-zero compute",
    )
    d.zone("z_clients", 20, 110, 260, 400, "MCP clients", "client", title_size=18)
    for i, (cid, lbl) in enumerate(
        [
            ("c_lg", "LangGraph\nOps Copilot"),
            ("c_adk", "Google ADK\nagent"),
            ("c_cd", "Claude Desktop"),
            ("c_st", "Streamlit\nconsole"),
        ]
    ):
        d.box(cid, 45, 160 + i * 85, 210, 65, lbl, "client")
    d.box("cf", 320, 180, 150, 70, "CloudFront", "edge")
    d.box("apigw", 560, 180, 180, 70, "API Gateway\nHTTP API", "edge")
    d.box("cognito", 330, 560, 180, 75, "Cognito\nOAuth 2.1 AS", "security")
    for cid in ("c_lg", "c_adk", "c_cd", "c_st"):
        d.arrow(f"a_{cid}", cid, (1, 0.5), "cf", (0, 0.5))
    d.arrow(
        "a_login",
        "z_clients",
        (0.5, 1),
        "cognito",
        (0, 0.5),
        "PKCE login",
        via=((150, 597),),
        dashed=True,
        color="#c92a2a",
    )
    d.arrow("a_cf_api", "cf", (1, 0.5), "apigw", (0, 0.5), "HTTPS")

    d.zone("z_vpc", 800, 120, 700, 650, "VPC · private subnets", "compute")
    d.box("mcp", 840, 180, 230, 70, "mcp-gateway\nFastMCP", "compute")
    d.box("core", 840, 330, 230, 70, "core-api\nFastAPI", "compute")
    d.box("sim", 840, 480, 230, 70, "screening-sim\nvendor simulator", "compute")
    d.box("workers", 840, 630, 230, 80, "workers\ningest · outbox · events", "compute")
    d.box("nat", 1230, 150, 220, 60, "NAT instance\nt4g.nano", "edge")
    d.box("rds", 1230, 380, 210, 100, "RDS PostgreSQL 16\n+ pgvector", "data")

    d.box("openai", 1600, 150, 230, 60, "OpenAI embeddings", "external")
    d.box("ddb", 1600, 260, 230, 70, "DynamoDB\nrate limits · breaker flags", "data")
    d.box("sqs", 1600, 380, 230, 70, "SQS + DLQ\ningest · domain events", "async")
    d.box("s3", 1600, 500, 230, 70, "S3\ncorpus documents", "data")
    d.box("secrets", 1600, 620, 230, 70, "Secrets Manager\nOpenAI key · DB creds", "security")

    d.arrow("a_api_mcp", "apigw", (1, 0.5), "mcp", (0, 0.5), "/mcp")
    d.arrow(
        "a_mcp_cog",
        "mcp",
        (0, 0.85),
        "cognito",
        (1, 0.5),
        "JWKS verify",
        dashed=True,
        color="#c92a2a",
    )
    d.arrow("a_mcp_core", "mcp", (0.5, 1), "core", (0.5, 0), "HTTP + deadline")
    d.arrow("a_core_sim", "core", (0.5, 1), "sim", (0.5, 0), "circuit breaker")
    d.arrow("a_mcp_ddb", "mcp", (1, 0.5), "ddb", (0, 0.3), "token bucket", via=((1150, 215),))
    d.arrow("a_core_rds", "core", (1, 0.5), "rds", (0, 0.5), "SQL")
    d.arrow("a_core_nat", "core", (1, 0.2), "nat", (0.5, 1), "query embed", dashed=True)
    d.arrow("a_nat_oai", "nat", (1, 0.5), "openai", (0, 0.5), "HTTPS")
    d.arrow("a_wk_rds", "workers", (1, 0.25), "rds", (0.5, 1), "upsert chunks")
    d.arrow(
        "a_sqs_wk", "sqs", (0, 0.5), "workers", (1, 0.75), "consume", via=((1530, 415), (1530, 690))
    )
    d.arrow("a_s3_sqs", "s3", (0.5, 0), "sqs", (0.5, 1), "ObjectCreated")
    d.text("n_secrets", 1600, 700, "read once at Lambda init", size=14, color="#495057")

    d.box("cw", 840, 830, 230, 70, "CloudWatch + X-Ray\nlogs · metrics · traces", "obs")
    d.box("cdeploy", 1230, 830, 210, 70, "CodeDeploy\ncanary 10% / 5 min", "obs")
    d.box("ecr", 1600, 830, 230, 70, "ECR\narm64 images", "obs")
    d.arrow("a_vpc_cw", "z_vpc", (0.15, 1), "cw", (0.5, 0), "OTel", dashed=True, color="#2f9e44")
    d.arrow(
        "a_cd_vpc",
        "cdeploy",
        (0.5, 0),
        "z_vpc",
        (0.62, 1),
        "alias shift",
        dashed=True,
        color="#2f9e44",
    )
    d.arrow("a_ecr_cd", "ecr", (0, 0.5), "cdeploy", (1, 0.5), "image")
    d.legend(40, 940, ALL_TIERS)
    return d


def request_lifecycle():
    d = Diagram()
    d.title(
        "One tool call — request lifecycle",
        "Every MCP tool call crosses the same middleware pipeline in mcp-gateway",
    )
    d.box("client", 40, 230, 220, 80, "MCP client\nBearer token", "client", shape="ellipse")
    row1 = [
        ("s1", "1 · Load shedding\nin-flight check"),
        ("s2", "2 · AuthN\nJWT via JWKS"),
        ("s3", "3 · Rate limit\nper client · DynamoDB"),
        ("s4", "4 · AuthZ\ntool scope check"),
        ("s5", "5 · Deadline\nbudget set"),
    ]
    for i, (sid, lbl) in enumerate(row1):
        d.box(
            sid,
            320 + i * 280,
            230,
            220,
            80,
            lbl,
            "compute" if sid not in {"s2", "s4"} else "security",
        )
    row2 = [
        ("s6", "6 · Tool handler\nPydantic-validated"),
        ("s7", "7 · core-api call\ntimeout · retry · breaker"),
        ("s8", "8 · PII masking\nby role"),
        ("s9", "9 · Audit log\nappend-only"),
        ("s10", "10 · Response\nstructured content"),
    ]
    for i, (sid, lbl) in enumerate(row2):
        tier = {"s7": "data", "s8": "security", "s9": "obs", "s10": "client"}.get(sid, "compute")
        d.box(sid, 1440 - i * 280, 450, 220, 80, lbl, tier)
    d.arrow("a_c_1", "client", (1, 0.5), "s1", (0, 0.5))
    for a, b in zip(["s1", "s2", "s3", "s4"], ["s2", "s3", "s4", "s5"], strict=False):
        d.arrow(f"a_{a}_{b}", a, (1, 0.5), b, (0, 0.5))
    d.arrow("a_s5_s6", "s5", (0.5, 1), "s6", (0.5, 0))
    for a, b in zip(["s6", "s7", "s8", "s9"], ["s7", "s8", "s9", "s10"], strict=False):
        d.arrow(f"a_{a}_{b}", a, (0, 0.5), b, (1, 0.5))
    d.arrow("a_s10_c", "s10", (0, 0.5), "client", (0.5, 1), via=((150, 490),))
    errs = [
        ("e1", "s1", "503 overloaded"),
        ("e2", "s2", "401 + WWW-Authenticate\n(resource metadata)"),
        ("e3", "s3", "429 + Retry-After"),
        ("e4", "s4", "403 insufficient_scope"),
    ]
    for i, (eid, sid, lbl) in enumerate(errs):
        d.box(eid, 320 + i * 280, 90, 220, 75, lbl, "security", size=16)
        d.arrow(f"a_{sid}_{eid}", sid, (0.5, 0), eid, (0.5, 1), dashed=True, color="#c92a2a")
    d.box("e7", 1160, 610, 220, 80, "breaker open →\nfast-fail / degraded", "security")
    d.arrow("a_s7_e7", "s7", (0.5, 1), "e7", (0.5, 0), dashed=True, color="#c92a2a")
    d.box(
        "note",
        320,
        610,
        760,
        80,
        "The deadline from step 5 travels with every downstream call:\neach hop gets min(remaining − margin, per-call cap)",
        "note",
    )
    d.text(
        "trace",
        40,
        720,
        "One trace ID spans steps 1–10, core-api, Postgres and OpenAI (OpenTelemetry).",
        size=16,
        color="#495057",
    )
    return d


def circuit_breaker():
    d = Diagram()
    d.title(
        "Circuit breaker — state machine",
        "One breaker per downstream per Lambda instance; shared force-open flag in DynamoDB",
    )
    d.box("closed", 80, 330, 260, 130, "CLOSED\ncalls flow", "obs", shape="ellipse", size=20)
    d.box("open", 880, 330, 260, 130, "OPEN\nfail fast", "security", shape="ellipse", size=20)
    d.box("half", 480, 120, 260, 130, "HALF-OPEN\ntrial calls", "async", shape="ellipse", size=20)
    d.arrow(
        "a_c_o",
        "closed",
        (1, 0.5),
        "open",
        (0, 0.5),
        "failure rate ≥ 50%\nover last 20 calls (min 10)",
        color="#c92a2a",
    )
    d.arrow(
        "a_o_h", "open", (0.75, 0.05), "half", (1, 0.35), "cool-down\n30 s elapsed", color="#e67700"
    )
    d.arrow(
        "a_h_c", "half", (0, 0.5), "closed", (0.5, 0), "3 trial calls\nsucceed", color="#2f9e44"
    )
    d.arrow(
        "a_h_o",
        "half",
        (0.8, 0.9),
        "open",
        (0.3, 0.05),
        "any trial\nfails",
        color="#c92a2a",
        dashed=True,
    )
    d.arrow(
        "a_c_c",
        "closed",
        (0.3, 0.98),
        "closed",
        (0.7, 0.98),
        "success or\nbelow threshold",
        via=((158, 540), (262, 540)),
        color="#2f9e44",
    )
    d.arrow(
        "a_o_o",
        "open",
        (0.3, 0.98),
        "open",
        (0.7, 0.98),
        "CircuitOpenError\n(no network call)",
        via=((958, 540), (1062, 540)),
        color="#c92a2a",
    )
    d.box("force", 1220, 140, 260, 90, "DynamoDB force-open flag\n(ops override)", "data")
    d.arrow("a_f_o", "force", (0.5, 1), "open", (1, 0.3), "any state →", dashed=True)
    d.box(
        "note",
        80,
        640,
        1060,
        110,
        "Defaults shown are configurable per downstream.  Emits metric breaker_state{dependency}\n"
        "and a structured log on every transition.  Retries never run while OPEN, and\n"
        "get_service_health exposes live state to MCP clients.",
        "note",
    )
    return d


def rag_pipeline():
    d = Diagram()
    d.title(
        "Knowledge base — ingestion and hybrid retrieval",
        "OpenAI text-embedding-3-large @ 1024 dims · pgvector HNSW + Postgres FTS · RRF · row-level security",
    )
    d.zone("z_ing", 20, 110, 1700, 250, "Ingestion — async", "async")
    steps = [
        ("i_s3", "S3 corpus\nmd · pdf · docx · yaml", "data"),
        ("i_sqs", "SQS\ningest queue", "async"),
        ("i_wk", "ingest-worker\nLambda", "compute"),
        ("i_parse", "Parse\nper format", "compute"),
        ("i_chunk", "Chunk\nsection-aware", "compute"),
        ("i_emb", "Embed\nOpenAI · batched", "external"),
        ("i_pg", "kb.chunks\nvector · tsvector", "data"),
    ]
    for i, (sid, lbl, tier) in enumerate(steps):
        d.box(sid, 45 + i * 238, 160, 195, 80, lbl, tier)
    for a, b in itertools.pairwise(steps):
        d.arrow(f"a_{a[0]}_{b[0]}", a[0], (1, 0.5), b[0], (0, 0.5))
    d.box("i_dlq", 283, 270, 195, 65, "DLQ\nafter 3 attempts", "security")
    d.arrow("a_dlq", "i_sqs", (0.5, 1), "i_dlq", (0.5, 0), dashed=True, color="#c92a2a")
    d.text(
        "n_idem",
        760,
        280,
        "idempotent upsert keyed by (doc sha256, chunk index)",
        size=16,
        color="#495057",
    )

    d.zone("z_q", 20, 400, 1700, 360, "Query — synchronous, per tool call", "client")
    d.box("q_tool", 45, 540, 200, 80, "search_knowledge_base\n(query, dept, k)", "client", size=16)
    d.box("q_emb", 290, 540, 190, 80, "Embed query\nOpenAI", "external")
    d.box("q_vec", 540, 460, 220, 80, "Vector top-k\npgvector HNSW", "data")
    d.box("q_fts", 540, 630, 220, 80, "Keyword top-k\nPostgres FTS", "data")
    d.box("q_rrf", 820, 540, 190, 80, "RRF fusion\nk = 60", "compute")
    d.box("q_rls", 1070, 540, 200, 80, "RLS filter\nclassification ≤ role", "security")
    d.box(
        "q_out", 1330, 530, 260, 100, "Cited chunks\ndoc · section · version\neffective date", "obs"
    )
    d.arrow("a_t_e", "q_tool", (1, 0.5), "q_emb", (0, 0.5))
    d.arrow("a_e_v", "q_emb", (1, 0.3), "q_vec", (0, 0.5))
    d.arrow("a_t_f", "q_tool", (0.5, 1), "q_fts", (0, 0.6), via=((145, 678),))
    d.arrow(
        "a_e_f",
        "q_emb",
        (0.6, 1),
        "q_fts",
        (0, 0.3),
        dashed=True,
        color="#c92a2a",
    )
    d.text(
        "n_degraded",
        160,
        712,
        "OpenAI down → keyword-only results, degraded: true",
        size=14,
        color="#c92a2a",
    )
    d.arrow("a_v_r", "q_vec", (1, 0.5), "q_rrf", (0, 0.3))
    d.arrow("a_f_r", "q_fts", (1, 0.5), "q_rrf", (0, 0.7))
    d.arrow("a_r_l", "q_rrf", (1, 0.5), "q_rls", (0, 0.5))
    d.arrow("a_l_o", "q_rls", (1, 0.5), "q_out", (0, 0.5))
    d.text(
        "n_sql",
        820,
        660,
        "vector + keyword + RRF + RLS run as ONE SQL statement against kb.chunks",
        size=16,
        color="#495057",
    )
    return d


def cicd_pipeline():
    d = Diagram()
    d.title(
        "CI/CD — GitHub Actions to AWS",
        "Keyless OIDC · SHA-pinned actions · scanned arm64 images · canary deploys with rollback",
    )
    d.zone("z_pr", 20, 110, 1360, 190, "Pull request · ci.yml", "client")
    pr = [
        ("p1", "PR opened\nConventional Commit", "client"),
        ("p2", "Lint & types\nruff · pyright", "compute"),
        ("p3", "Tests\nunit · integration\ncontract", "compute"),
        ("p4", "Security\nruff-S · pip-audit\ngitleaks", "security"),
        ("p5", "Docker build\n+ Trivy scan", "obs"),
    ]
    for i, (pid, lbl, tier) in enumerate(pr):
        d.box(pid, 45 + i * 265, 170, 215, 95, lbl, tier)
    for a, b in itertools.pairwise(pr):
        d.arrow(f"a_{a[0]}_{b[0]}", a[0], (1, 0.5), b[0], (0, 0.5))

    d.zone("z_main", 20, 360, 1700, 440, "main branch · cd.yml · OIDC → AWS", "obs", title_dx=1310)
    d.box("m1", 45, 500, 200, 85, "Push to ECR\n(OIDC role)", "obs")
    d.box("m2", 300, 500, 210, 85, "cdk deploy\n+ cdk-nag", "compute")
    d.box("m3", 565, 500, 220, 85, "CodeDeploy canary\n10% for 5 min", "obs")
    d.box("m4", 845, 475, 200, 135, "alarms\nhealthy?", "async", shape="diamond")
    d.box("m5", 1140, 400, 210, 80, "Promote\n100% traffic", "obs")
    d.box("m6", 1140, 640, 210, 80, "Automatic\nrollback", "security")
    d.box("m7", 1420, 400, 270, 80, "E2E + Locust smoke\nagainst live stack", "client")
    d.arrow(
        "a_p5_m1", "p5", (0.5, 1), "m1", (0.5, 0), "merge to main", via=((1182, 330), (145, 330))
    )
    d.arrow("a_m1_m2", "m1", (1, 0.5), "m2", (0, 0.5))
    d.arrow("a_m2_m3", "m2", (1, 0.5), "m3", (0, 0.5))
    d.arrow("a_m3_m4", "m3", (1, 0.5), "m4", (0, 0.5))
    d.arrow(
        "a_m4_m5",
        "m4",
        (0.5, 0),
        "m5",
        (0, 0.5),
        "yes",
        via=((945, 440), (1060, 440)),
        color="#2f9e44",
    )
    d.arrow(
        "a_m4_m6",
        "m4",
        (0.5, 1),
        "m6",
        (0, 0.5),
        "no",
        via=((945, 680), (1060, 680)),
        color="#c92a2a",
    )
    d.arrow("a_m5_m7", "m5", (1, 0.5), "m7", (0, 0.5))
    d.box(
        "note",
        45,
        650,
        740,
        120,
        "Error-rate and p95-latency alarms gate the canary.  A failed\n"
        "alarm shifts traffic back to the previous Lambda version\n"
        "with no human action.  release-please tags each release.",
        "note",
    )
    return d


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in [
        ("system-architecture", system_architecture),
        ("request-lifecycle", request_lifecycle),
        ("circuit-breaker", circuit_breaker),
        ("rag-pipeline", rag_pipeline),
        ("cicd-pipeline", cicd_pipeline),
    ]:
        fn().save(out / f"{name}.excalidraw")
        print("wrote", name)
