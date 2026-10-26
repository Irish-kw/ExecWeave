from __future__ import annotations

_COMPONENT_SEAM = """    const nodes=[...nodeById.values()].filter(node=>topo.spec.has(node.id));
    const edges=[...edgeById.values()].filter(edge=>topo.spec.has(edge.source)&&topo.spec.has(edge.target));
    const componentOf=execweaveComponents(nodes,edges);"""
_COMPONENT_REPLACEMENT = """    const nodes=[...nodeById.values()].filter(node=>topo.spec.has(node.id));
    const edges=[...edgeById.values()].filter(edge=>topo.spec.has(edge.source)&&topo.spec.has(edge.target));
    // The orphan file summary is connected to the root by a viewer-only,
    // non-causal OBSERVED_FILES bridge solely so the inspector can expose the
    // collapsed evidence.  That presentation bridge must not promote genuinely
    // detached evidence into the execution spine for packing.
    const detachedClusterIds=new Set(nodes.filter(node=>{
      const attrs=node&&typeof node.attributes==='object'&&node.attributes?node.attributes:{};
      return node.id==='viewer-cluster:orphan-files'||attrs.reason==='orphan_file_directory_nodes';
    }).map(node=>node.id));
    const layoutEdges=edges.filter(edge=>!detachedClusterIds.has(edge.source)&&!detachedClusterIds.has(edge.target));
    const componentOf=execweaveComponents(nodes,layoutEdges);"""


def inject_layout_v2_detached_cluster_policy(html: str) -> str:
    """Keep presentation-only orphan clusters out of execution-spine packing."""

    if html.count(_COMPONENT_SEAM) != 1:
        raise RuntimeError("layout-v2 detached-cluster component seam changed")
    return html.replace(_COMPONENT_SEAM, _COMPONENT_REPLACEMENT, 1)
