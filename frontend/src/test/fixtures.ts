import { buildDecisionRows, buildGraphIndex } from '../utils/model';
import { MOCK_DECISIONS, MOCK_GRAPH } from '../api/mocks';

export const index = buildGraphIndex(MOCK_GRAPH);
export const rows = buildDecisionRows(MOCK_DECISIONS, index);
