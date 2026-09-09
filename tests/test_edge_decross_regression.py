from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from execweave.dashboard_shell import DASHBOARD_HTML
from execweave.viewer_edge_decross import EDGE_DECROSS_SCRIPT
from execweave.viewer_layout_geometry import LAYOUT_GEOMETRY_SCRIPT


def _node() -> str:
    executable = shutil.which("node")
    assert executable is not None
    return executable


def test_shared_dashboard_installs_edge_decrossover() -> None:
    assert "window.__execweaveEdgeDecross" in DASHBOARD_HTML
    assert "protectedNetworkCrossingsAvoided" in DASHBOARD_HTML


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_non_network_edge_detours_while_network_route_stays_fixed() -> None:
    script = r"""
global.window={};
global.nodeById=new Map([
  ['process:claude',{id:'process:claude',type:'process'}],
  ['agent:root',{id:'agent:root',type:'agent'}],
  ['process:gh',{id:'process:gh',type:'process'}],
  ['endpoint:external',{id:'endpoint:external',type:'network_endpoint'}],
]);
global.positions=new Map([
  ['process:claude',{x:0,y:0}],
  ['agent:root',{x:100,y:0}],
]);
global.edgeId=edge=>edge.id;
const launch={id:'launch',source:'process:claude',target:'agent:root',relation:'LAUNCHED'};
const network={id:'network',source:'process:gh',target:'endpoint:external',relation:'CONNECTED_TO'};
global.edgeById=new Map([['launch',launch],['network',network]]);
global.execweaveTopology={width:new Map(),height:new Map()};
global.execweaveWidthOf=()=>0;global.execweaveHeightOf=()=>0;
global.execweaveRoute=edge=>edge.id==='launch'
  ?{d:'M 0 0 L 100 0',labelX:50,labelY:-8,kind:'forward',bundle:null}
  :{d:'M 50 -50 L 50 50',labelX:50,labelY:-8,kind:'forward',bundle:null};
""" + LAYOUT_GEOMETRY_SCRIPT + "\n" + EDGE_DECROSS_SCRIPT + r"""
const launchRoute=execweaveRoute(launch),networkRoute=execweaveRoute(network);
const metrics=execweaveGeometry.measure([], [
  {...launch,d:launchRoute.d},
  {...network,d:networkRoute.d},
]);
process.stdout.write(JSON.stringify({launchRoute,networkRoute,metrics}));
"""
    result = subprocess.run(
        [_node(), "-"],
        input=script,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    payload = json.loads(result.stdout)
    assert payload["launchRoute"]["geometryKind"] == "edge-decrossover"
    assert payload["launchRoute"]["protectedNetworkCrossingsAvoided"] == 1
    assert payload["launchRoute"]["d"] != "M 0 0 L 100 0"
    assert payload["networkRoute"]["d"] == "M 50 -50 L 50 50"
    assert payload["metrics"]["EDGE_CROSSINGS"] == 0
