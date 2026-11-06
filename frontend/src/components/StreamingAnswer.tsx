import { useEffect, useRef, useState } from 'react';
import type { AnswerBlock } from '../api/dialogue';

const CHARACTER_DELAY_MS = 18;

function characterCount(value: string): number {
  return Array.from(value).length;
}

function visibleText(value: string, length: number): string {
  return Array.from(value).slice(0, length).join('');
}

export function StreamingAnswer({
  blocks,
  streaming,
}: {
  blocks: AnswerBlock[];
  streaming: boolean;
}) {
  const hasStreamed = useRef(streaming);
  const [visibleLengths, setVisibleLengths] = useState(() =>
    blocks.map(block => streaming ? 0 : characterCount(block.text)),
  );
  const blockSignature = blocks.map(block => `${block.blockIndex}:${block.text}`).join('\u0000');

  useEffect(() => {
    if (streaming) hasStreamed.current = true;
  }, [streaming]);

  useEffect(() => {
    if (!hasStreamed.current) return;

    const firstIncomplete = blocks.findIndex(
      (block, index) => (visibleLengths[index] ?? 0) < characterCount(block.text),
    );
    if (firstIncomplete < 0) return;

    const timer = window.setTimeout(() => {
      setVisibleLengths(current => {
        const next = [...current];
        while (next.length < blocks.length) next.push(0);
        const total = characterCount(blocks[firstIncomplete]?.text ?? '');
        next[firstIncomplete] = Math.min((next[firstIncomplete] ?? 0) + 1, total);
        return next;
      });
    }, CHARACTER_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [blockSignature, blocks, visibleLengths]);

  const typing = blocks.some(
    (block, index) => (visibleLengths[index] ?? 0) < characterCount(block.text),
  );

  return <div className="streaming-answer" aria-live="polite">
    {blocks.map((block, index) => <p key={block.blockIndex}>
      {visibleText(block.text, visibleLengths[index] ?? 0)}
      {typing && index === blocks.findIndex(
        (item, itemIndex) => (visibleLengths[itemIndex] ?? 0) < characterCount(item.text),
      ) && <span className="typing-cursor" aria-hidden="true" />}
    </p>)}
  </div>;
}
