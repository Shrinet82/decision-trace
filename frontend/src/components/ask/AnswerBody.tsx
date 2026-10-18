import React, { useMemo } from 'react';
import { Link } from '../../router';
import { decisionHref, splitDecisionCodes } from '../../utils/links';
import type { Citation } from '../../api/types';
import {
  citeAnchor,
  parseAnswer,
  withCitationMarks,
  type InlineToken,
} from '../../utils/answer';

export interface AnswerBodyProps {
  answer: string;
  citations: Citation[];
  turnKey: string;
  onCite: (anchorId: string) => void;
}

export const AnswerBody: React.FC<AnswerBodyProps> = ({ answer, citations, turnKey, onCite }) => {
  const blocks = useMemo(() => {
    const used = new Set<number>();
    return parseAnswer(answer).map((block) =>
      block.kind === 'paragraph'
        ? { ...block, tokens: withCitationMarks(block.tokens, citations, used) }
        : {
            ...block,
            items: block.items.map((item) => ({
              tokens: withCitationMarks(item.tokens, citations, used),
              children: item.children.map((c) => withCitationMarks(c, citations, used)),
            })),
          }
    );
  }, [answer, citations]);

  const renderTokens = (tokens: InlineToken[]) =>
    tokens.map((token, i) => {
      switch (token.kind) {
        case 'bold':
          return (
            <strong key={i} className="font-semibold text-text">
              {token.text}
            </strong>
          );
        case 'italic':
          return <em key={i}>{token.text}</em>;
        case 'code':
          return (
            <code key={i} className="rounded-[4px] bg-subtle px-1 font-mono text-[12px]">
              {token.text}
            </code>
          );
        case 'cite':
          return (
            <sup key={i} className="ml-0.5">
              <a
                href={`#${citeAnchor(turnKey, token.index)}`}
                aria-label={`Source ${token.index + 1}`}
                onClick={(e) => {
                  e.preventDefault();
                  onCite(citeAnchor(turnKey, token.index));
                }}
                className="text-[11px] font-semibold text-accent hover:underline"
              >
                {token.index + 1}
              </a>
            </sup>
          );
        default:
          return (
            <React.Fragment key={i}>
              {splitDecisionCodes(token.text).map((part, j) =>
                part.code ? (
                  <Link key={j} to={decisionHref(part.code)} className="font-medium text-accent hover:underline">
                    {part.text}
                  </Link>
                ) : (
                  <React.Fragment key={j}>{part.text}</React.Fragment>
                )
              )}
            </React.Fragment>
          );
      }
    });

  return (
    <div className="flex flex-col gap-3 text-base text-[#2A2C30]">
      {blocks.map((block, i) =>
        block.kind === 'paragraph' ? (
          <p key={i} className="m-0">
            {renderTokens(block.tokens)}
          </p>
        ) : (
          React.createElement(
            block.ordered ? 'ol' : 'ul',
            { key: i, className: 'm-0 flex flex-col gap-2 pl-5' },
            block.items.map((item, j) => (
              <li key={j}>
                {renderTokens(item.tokens)}
                {item.children.length > 0 && (
                  <ul className="m-0 mt-1 flex list-disc flex-col gap-1 pl-5">
                    {item.children.map((child, k) => (
                      <li key={k}>{renderTokens(child)}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))
          )
        )
      )}
    </div>
  );
};
