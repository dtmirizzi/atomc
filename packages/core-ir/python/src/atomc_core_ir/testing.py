"""Reusable Hypothesis strategies for generating valid ``SystemIR`` documents.

Kept in the importable package (not ``tests/``) so other packages (daemon, contract tests)
can reuse them::

    from atomc_core_ir.testing import system_ir_strategy

    @given(system_ir_strategy())
    def test_roundtrip(ir):
        assert SystemIR.load(ir.dump()).dump() == ir.dump()
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from hypothesis import strategies as st

from .common import Artifact, NodeMeta
from .document import DocumentMeta, SystemIR
from .electrical import Assertion, Component, Electrical, ElectricalSource, ErcViolation, Net, Pin
from .fabrication import FabQuote, Fabrication, PcbSpec
from .firmware import Firmware, FwTarget, MemoryRegion, PeriphMap, Signal, TestSuite
from .gates import Evidence, GateResult, Gates
from .keyboard import Key, Keyboard, Matrix, Qmk, Usb
from .layout import Hole, Keepout, Layout, Outline, Placement, TestPad
from .mechanical import ComponentBBox, Mechanical, MechCheck
from .orders import Order, OrderLine, Orders
from .provenance import Provenance, ProvNode
from .simulation import Capture, Scenario, Simulation
from .sourcing import BomLine, Budget, Offer, PriceBreak, Sourcing

_HEX = "0123456789abcdef"
_TIMESTAMP: st.SearchStrategy[datetime] = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2035, 1, 1),
    timezones=st.just(UTC),
).map(lambda dt: dt.replace(microsecond=0))

_TS = st.integers(min_value=0, max_value=50)
_SHA = st.text(alphabet=_HEX, min_size=64, max_size=64).map(lambda h: f"sha256:{h}")


def sha256_strategy() -> st.SearchStrategy[str]:
    """A valid ``sha256:<64 hex>`` string."""
    return _SHA


def _unique_ids(prefix: str, min_size: int, max_size: int) -> st.SearchStrategy[list[str]]:
    return st.lists(
        st.integers(min_value=0, max_value=1_000_000).map(lambda i: f"{prefix}:{i}"),
        min_size=min_size,
        max_size=max_size,
        unique=True,
    )


def _pin_names(prefix: str, count: int) -> st.SearchStrategy[list[str]]:
    return st.lists(
        st.integers(min_value=0, max_value=100).map(lambda i: f"{prefix}{i}"),
        min_size=count,
        max_size=count,
        unique=True,
    )


def _node_meta() -> st.SearchStrategy[NodeMeta]:
    return st.builds(NodeMeta, rev=_TS)


def _artifact(artifact_id: str, produced_at: datetime) -> st.SearchStrategy[Artifact]:
    return st.builds(
        Artifact,
        id=st.just(artifact_id),
        kind=st.just("elf"),
        path=st.just("build/fw.elf"),
        sha256=_SHA,
        bytes=st.integers(min_value=0, max_value=1_000_000),
        produced_by=st.just("plugin:renode@0.1.0"),
        produced_at=st.just(produced_at),
    )


def system_ir_strategy() -> st.SearchStrategy[SystemIR]:
    """A strategy producing valid, referentially-closed ``SystemIR`` documents."""
    return _system_ir_composite()


@st.composite
def _system_ir_composite(draw: Any) -> SystemIR:
    net_ids = draw(_unique_ids("net", 1, 3))
    comp_ids = draw(_unique_ids("comp", 1, 3))
    pad_ids = draw(_unique_ids("pad", 1, 3))
    art_ids = draw(_unique_ids("art", 1, 1))
    now = draw(_TIMESTAMP)

    components = []
    for comp_id in comp_ids:
        pins = draw(
            st.lists(
                st.builds(
                    Pin,
                    number=st.text(min_size=1, max_size=3),
                    net_ref=st.one_of(st.none(), st.sampled_from(net_ids)),
                ),
                max_size=3,
            )
        )
        components.append(
            Component(
                id=comp_id,
                designator=comp_id.split(":")[1],
                mpn=draw(st.one_of(st.none(), st.text(min_size=1, max_size=8))),
                pins=pins,
            )
        )
    nets = [Net(id=n, name=n.split(":")[1]) for n in net_ids]

    electrical = Electrical(
        meta_=draw(_node_meta()),
        source=ElectricalSource(kind="atopile", entry="main.ato:App"),
        components=components,
        nets=nets,
        assertions=[Assertion(id="assert:A1", expr="a", status="pass")],
        erc=[
            ErcViolation(
                id="erc:E1",
                rule="no_unconnected",
                severity="warning",
                message="x",
                refs=[draw(st.sampled_from(comp_ids))],
            )
        ],
    )

    outline: list[list[float]] = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
    layout = Layout(
        meta_=draw(_node_meta()),
        outline=Outline(polygon=outline),
        placements=[
            Placement(
                component_ref=c,
                x=draw(st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False)),
                y=draw(st.floats(min_value=0, max_value=50, allow_nan=False, allow_infinity=False)),
                side="top",
            )
            for c in comp_ids
        ],
        test_pads=[
            TestPad(
                id=p,
                net_ref=draw(st.sampled_from(net_ids)),
                x=float(i),
                y=float(i),
            )
            for i, p in enumerate(pad_ids)
        ],
        mounting_holes=[Hole(id="hole:H1", x=1.0, y=1.0, diameter_mm=3.2, plated=False)],
        keepouts=[
            Keepout(
                id="keepout:K1",
                polygon=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
                side="top",
                kind="component",
            )
        ],
    )

    rows = draw(st.integers(min_value=1, max_value=3))
    cols = draw(st.integers(min_value=1, max_value=3))
    row_pins = draw(_pin_names("B", rows))
    col_pins = draw(_pin_names("A", cols))
    positions = draw(
        st.lists(
            st.tuples(st.integers(0, rows - 1), st.integers(0, cols - 1)),
            unique=True,
            max_size=rows * cols,
        )
    )
    keys = [
        Key(
            id=f"key:K{r}_{c}",
            row=r,
            col=c,
            switch_ref=draw(st.sampled_from(comp_ids)),
            diode_ref=draw(st.sampled_from(comp_ids)),
            keycode_default="KC_A",
        )
        for (r, c) in positions
    ]
    keyboard = Keyboard(
        meta_=draw(_node_meta()),
        matrix=Matrix(
            rows=rows,
            cols=cols,
            diode_direction="COL2ROW",
            row_pins=row_pins,
            col_pins=col_pins,
        ),
        keys=keys,
        usb=Usb(vid="0xFEED", pid="0x0001", manufacturer="atomc", product="pad"),
        qmk=Qmk(keyboard_path="atomc/pad"),
    )

    artifact = draw(_artifact(art_ids[0], now))
    firmware = Firmware(
        meta_=draw(_node_meta()),
        targets=[
            FwTarget(
                id="fw:main",
                mcu="STM32F411CEU6",
                core="cortex-m4f",
                memory=[MemoryRegion(name="flash", origin=0x08000000, length=512 * 1024)],
                framework="qmk",
                source_dir="qmk",
                artifacts=[artifact],
            )
        ],
        peripherals=[
            PeriphMap(
                id="periph:usart1",
                kind="uart",
                base_address=0x40011000,
                signals=[Signal(name="TX", pin="A9", net_ref=draw(st.sampled_from(net_ids)))],
            )
        ],
        suites=[TestSuite(id="suite:matrix", path="tests/test_matrix.py")],
    )

    scenario_ids = draw(_unique_ids("sim", 1, 2))
    simulation = Simulation(
        meta_=draw(_node_meta()),
        platform={"repl_path": "build/atomc.repl"},
        scenarios=[Scenario(id=s, description="boot") for s in scenario_ids],
        captures=[
            Capture(
                id="cap:uart",
                kind="uart",
                path="build/uart.log",
                scenario_ref=draw(st.sampled_from(scenario_ids)),
            )
        ],
    )

    mechanical = Mechanical(
        meta_=draw(_node_meta()),
        component_bboxes=[
            ComponentBBox(component_ref=c, min=[0.0, 0.0, 0.0], max=[1.0, 1.0, 1.0])
            for c in comp_ids
        ],
        checks=[MechCheck(id="check:C1", kind="clearance", status="pass")],
    )

    offer_ids = draw(_unique_ids("offer", 1, 2))
    offers = [
        Offer(
            id=o,
            vendor="lcsc",
            sku=f"C{1000 + i}",
            stock=draw(st.integers(min_value=0, max_value=1000)),
            price_breaks=[PriceBreak(qty=1, unit_price_minor=10)],
            fetched_at=now,
        )
        for i, o in enumerate(offer_ids)
    ]
    bom = [
        BomLine(
            id="bom:U1",
            component_refs=[comp_ids[0]],
            qty_per_unit=1,
            offers=offers,
            chosen_offer_ref=draw(st.sampled_from(offer_ids)),
        )
    ]
    sourcing = Sourcing(
        meta_=draw(_node_meta()),
        build_qty=draw(st.integers(min_value=1, max_value=10)),
        budget=Budget(per_unit_minor=1000),
        bom=bom,
    )

    fabrication = Fabrication(
        meta_=draw(_node_meta()),
        pcb=PcbSpec(
            layers=2,
            width_mm=80.0,
            height_mm=80.0,
            thickness_mm=1.6,
            finish="HASL",
            color="black",
            qty=5,
        ),
        quotes=[
            FabQuote(
                id="fab:jlc1",
                fab="jlcpcb",
                total_minor=500,
                lead_time_days=7,
                fetched_at=now,
            )
        ],
    )

    orders = Orders(
        meta_=draw(_node_meta()),
        orders=[
            Order(
                id="order:1",
                vendor="lcsc",
                kind="parts",
                status="draft",
                lines=[OrderLine(sku="C1525", qty=5, unit_price_minor=100)],
                total_minor=500,
            )
        ],
    )

    gate = GateResult(
        id="gate:bom.all_in_stock",
        status="PASS",
        plugin="plugin:sourcing@0.1.0",
        owner_agent="ops-agent",
        evaluated_at=now,
        ir_rev=1,
        summary="ok",
        evidence=[Evidence(kind="text", message="all in stock")],
        refs=[comp_ids[0]],
    )
    gates = Gates(meta_=draw(_node_meta()), results={"bom.all_in_stock": gate})

    provenance = Provenance(
        meta_=draw(_node_meta()),
        nodes={
            "atopile.compile": ProvNode(
                producer="plugin:atopile@0.1.0",
                inputs_hash=draw(_SHA),
                outputs_hash=draw(_SHA),
                ran_at=now,
                duration_ms=5,
            )
        },
    )

    meta = DocumentMeta(
        project_id="proj:test",
        name="test",
        created_at=now,
        modified_at=now,
        atomc_version="0.1.0",
    )
    return SystemIR(
        meta=meta,
        electrical=electrical,
        layout=layout,
        keyboard=keyboard,
        firmware=firmware,
        simulation=simulation,
        mechanical=mechanical,
        sourcing=sourcing,
        fabrication=fabrication,
        orders=orders,
        gates=gates,
        provenance=provenance,
    )


def minimal_system_ir() -> SystemIR:
    """A deterministic meta-only document (used by fixtures/tests)."""
    return SystemIR.empty("proj:minimal", "minimal")
