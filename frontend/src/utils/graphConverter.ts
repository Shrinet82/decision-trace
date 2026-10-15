import type { ElementsDefinition, NodeDefinition, EdgeDefinition } from 'cytoscape';
import type { GraphPath, Citation } from '../api/types';
import { getSystemLine } from '../config/lines';

export interface ConvertedGraph {
  elements: ElementsDefinition;
  nodeCount: number;
  edgeCount: number;
  omittedCount: number;
}

/**
 * Maps a GraphPath to Cytoscape ElementsDefinition with node and edge attributes.
 */
export function convertGraphPathToCytoscape(
  graphPath: GraphPath | undefined,
  citations: Citation[] = [],
  isDark = false
): ConvertedGraph {
  if (!graphPath || !graphPath.nodes) {
    return {
      elements: { nodes: [], edges: [] },
      nodeCount: 0,
      edgeCount: 0,
      omittedCount: 0,
    };
  }

  const citedIds = new Set(citations.map((c) => c.id));

  // Build a lookup of system for decisions if edge exists
  const decisionToSystemMap = new Map<string, string>();
  for (const edge of graphPath.edges || []) {
    if (edge.type === 'about_system') {
      decisionToSystemMap.set(edge.source, edge.target);
    }
  }

  const nodes: NodeDefinition[] = graphPath.nodes.map((node) => {
    const label = node.label || 'Unknown';
    const props = node.properties || {};
    const title = (props.title as string) || (props.name as string) || (props.ticket_id as string) || node.id;
    const isCited = citedIds.has(node.id) || citedIds.has(title);

    let nodeType = label.toLowerCase();
    if (label === 'Decision') nodeType = 'decision';
    else if (label === 'Person') nodeType = 'person';
    else if (label === 'System') nodeType = 'system';
    else if (label === 'Ticket') nodeType = 'ticket';
    else if (label === 'Meeting') nodeType = 'meeting';

    // Determine system color for decisions
    const systemName =
      (props.system as string) || decisionToSystemMap.get(node.id);
    const lineConfig = getSystemLine(systemName);
    const nodeColor = isDark ? lineConfig.darkColor : lineConfig.lightColor;

    // Truncate long display label for clean graph layout
    const displayLabel =
      title.length > 32 ? `${title.slice(0, 30)}…` : title;

    return {
      data: {
        id: node.id,
        label: displayLabel,
        fullTitle: title,
        rawLabel: label,
        nodeType,
        isCited,
        systemName,
        lineColor: nodeColor,
        status: (props.status as string) || 'active',
        rationale: (props.rationale as string) || '',
        properties: props,
      },
    };
  });

  const edges: EdgeDefinition[] = (graphPath.edges || []).map((edge, index) => {
    let edgeLabel = edge.type;
    let edgeStyle = 'solid';
    let edgeColor = isDark ? '#9AA9B7' : '#52606D';

    if (edge.type === 'supersedes') {
      edgeLabel = 'replaces';
      edgeStyle = 'solid';
    } else if (edge.type === 'contradicts') {
      edgeLabel = 'conflicts with';
      edgeStyle = 'dashed';
      edgeColor = isDark ? '#E55353' : '#C62828';
    } else if (edge.type === 'decided_by') {
      edgeLabel = 'decided by';
    } else if (edge.type === 'about_system') {
      edgeLabel = 'about';
    } else if (edge.type === 'based_on') {
      edgeLabel = 'based on';
    }

    return {
      data: {
        id: `edge-${index}-${edge.source}-${edge.target}`,
        source: edge.source,
        target: edge.target,
        type: edge.type,
        label: edgeLabel,
        edgeStyle,
        edgeColor,
        properties: edge.properties || {},
      },
    };
  });

  return {
    elements: { nodes, edges },
    nodeCount: nodes.length,
    edgeCount: edges.length,
    omittedCount: graphPath.omitted_count || 0,
  };
}
