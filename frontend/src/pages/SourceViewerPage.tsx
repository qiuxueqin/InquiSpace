import { Alert, Button, Empty, Spin } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { isEvidenceView, isSourceView, isTextLinesView } from '../api/materials';
import type { EvidenceView, SourceView, TextLinesView } from '../api/materials';
import { request } from '../api/client';
import { recordLearningEvent } from '../api/p5';
import { useAuth } from '../auth/useAuth';

export function SourceViewerPage() {
  const [params] = useSearchParams();
  const evidenceId = params.get('evidenceId');
  const sessionId = params.get('sessionId');
  const { session: auth } = useAuth();
  const [evidence, setEvidence] = useState<EvidenceView | null>(null);
  const [source, setSource] = useState<SourceView | null>(null);
  const [text, setText] = useState<TextLinesView | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!evidenceId) return;
    const controller = new AbortController();
    void (async () => {
      try {
        const evidenceResult = await request(`/api/v1/evidence/${encodeURIComponent(evidenceId)}`, isEvidenceView, { signal: controller.signal });
        setEvidence(evidenceResult.data);
        const sourceResult = await request(`/api/v1/sources/${encodeURIComponent(evidenceResult.data.sourceId)}`, isSourceView, { signal: controller.signal });
        setSource(sourceResult.data);
        if (sourceResult.data.fileType === 'txt') {
          const start = evidenceResult.data.startLine ?? 1;
          const limit = Math.max(1, (evidenceResult.data.endLine ?? start) - start + 1);
          const textResult = await request(`/api/v1/sources/${encodeURIComponent(sourceResult.data.id)}/text?startLine=${start}&limit=${limit}`, isTextLinesView, { signal: controller.signal });
          setText(textResult.data);
        }
        if (sessionId && auth?.user.role === 'student' && auth.csrfToken) {
          await recordLearningEvent(sessionId, { type: 'source_open', sourceId: sourceResult.data.id }, auth.csrfToken, controller.signal);
        }
      } catch (caught) {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '无法读取资料。');
      }
    })();
    return () => controller.abort();
  }, [auth?.csrfToken, auth?.user.role, evidenceId, sessionId]);

  if (!evidenceId) return <Empty description="缺少引用标识，无法打开原文。" />;
  if (error) return <Alert type="error" showIcon message="无法打开原文" description={error} />;
  if (!evidence || !source) return <Spin tip="正在读取原文"><div className="source-viewer-loading" /></Spin>;
  return <main className="source-viewer"><div className="page-heading"><div><h1>{source.fileName}</h1><p>{evidence.sourceLabel}</p></div></div>{source.fileType === 'txt' ? <TxtViewer evidence={evidence} text={text} /> : <PdfViewer evidence={evidence} source={source} />}</main>;
}

function TxtViewer({ evidence, text }: { evidence: EvidenceView; text: TextLinesView | null }) {
  if (!text) return <Spin tip="正在读取文本"><div className="source-viewer-loading" /></Spin>;
  return <section className="card source-text" aria-label="TXT 原文">{text.lines.map((line, index) => {
    const lineNo = text.startLine + index;
    const highlighted = lineNo >= (evidence.startLine ?? lineNo) && lineNo <= (evidence.endLine ?? lineNo);
    return <div key={lineNo} className={highlighted ? 'source-line highlighted' : 'source-line'}><span>{lineNo}</span><pre>{line || ' '}</pre></div>;
  })}</section>;
}

function PdfViewer({ evidence, source }: { evidence: EvidenceView; source: SourceView }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState('正在打开 PDF…');
  const [error, setError] = useState('');
  useEffect(() => {
    let document: PDFDocumentProxy | undefined;
    let cancelled = false;
    void (async () => {
      try {
        const pdfjs = await import('pdfjs-dist');
        pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString();
        document = await pdfjs.getDocument(`/api/v1/sources/${encodeURIComponent(source.id)}/file`).promise;
        const pageNo = evidence.pageNo ?? 1;
        const page = await document.getPage(pageNo);
        if (cancelled || !canvas.current) return;
        const viewport = page.getViewport({ scale: 1.45 });
        const context = canvas.current.getContext('2d');
        if (!context) throw new Error('浏览器无法创建 PDF 画布。');
        canvas.current.width = viewport.width;
        canvas.current.height = viewport.height;
        await page.render({ canvas: canvas.current, canvasContext: context, viewport }).promise;
        setStatus(`第 ${pageNo} 页`);
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : 'PDF 打开失败。');
      }
    })();
    return () => { cancelled = true; void document?.destroy(); };
  }, [evidence.pageNo, source.id]);
  if (error) return <Alert type="error" showIcon message="PDF 打开失败" description={error} action={<Button href={`/api/v1/sources/${encodeURIComponent(source.id)}/file`} target="_blank">在新窗口打开</Button>} />;
  return <section className="card pdf-viewer"><p>{status}</p><canvas ref={canvas} aria-label={`PDF ${status}`} /></section>;
}
