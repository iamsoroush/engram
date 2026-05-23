import React from "react";
import type { CaptureItem } from "../types";
import { CaptureMetadataSummary, generatedMetadataFor, metadataDisplay, metadataRecord, metadataText } from "../metadata";
import { getCachedCapture } from "../storage";
import { Card, Dialog } from "../ui";
import { StatusBadge } from "./StatusBadges";

/**
 * Shows the best available source preview, preferring cached local blobs before
 * requesting protected backend file content.
 */
export function CaptureRawPreview({
  item,
  onResolveFile,
}: {
  item: CaptureItem;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const [cachedUrl, setCachedUrl] = React.useState("");
  const [resolvedUrl, setResolvedUrl] = React.useState("");
  const [noteText, setNoteText] = React.useState("");
  const metadata = metadataRecord(item.metadata);
  const thumbnail = metadataDisplay(metadata.thumbnail || metadata.thumbnail_url || metadata.thumbnailUrl);
  const isAudio = item.type === "audio" || item.type === "voice";
  const fileEndpoint = item.fileEndpoint || (item.sourceUrl?.startsWith("/api/v1/") && item.sourceUrl.endsWith("/file") ? item.sourceUrl : "");

  React.useEffect(() => {
    let revoked = false;
    setCachedUrl("");
    setNoteText("");
    getCachedCapture(item.id)
      .then((cached) => {
        if (!cached || revoked) return;
        const url = URL.createObjectURL(cached.blob);
        setCachedUrl(url);
        if (item.type === "note") void cached.blob.text().then((text) => !revoked && setNoteText(text));
      })
      .catch(() => undefined);
    return () => {
      revoked = true;
    };
  }, [item.id, item.type]);

  React.useEffect(() => {
    let cancelled = false;
    setResolvedUrl("");
    if (!fileEndpoint) return;
    onResolveFile(fileEndpoint)
      .then((url) => {
        if (!cancelled) setResolvedUrl(url);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [fileEndpoint, onResolveFile]);

  React.useEffect(() => {
    return () => {
      if (cachedUrl) URL.revokeObjectURL(cachedUrl);
    };
  }, [cachedUrl]);

  React.useEffect(() => {
    return () => {
      if (resolvedUrl.startsWith("blob:")) URL.revokeObjectURL(resolvedUrl);
    };
  }, [resolvedUrl]);

  const directSourceUrl = item.sourceUrl?.startsWith("/api/v1/") ? "" : item.sourceUrl;
  const sourceUrl = cachedUrl || resolvedUrl || directSourceUrl || item.url || "";

  if (item.type === "note") {
    return <p className="capture-raw-text">{noteText || item.detail}</p>;
  }

  if (item.type === "photo") {
    return sourceUrl || thumbnail ? (
      <img alt={item.sourceName} className="capture-raw-photo" src={sourceUrl || thumbnail} />
    ) : (
      <div className="capture-raw-placeholder">Photo preview unavailable</div>
    );
  }

  if (isAudio) {
    return sourceUrl ? (
      <audio className="capture-raw-audio" controls src={sourceUrl} />
    ) : (
      <div className="capture-raw-placeholder">Audio preview unavailable</div>
    );
  }

  return null;
}

/**
 * Full source viewer used from both the live capture feed and inline review workspace.
 * It mirrors CaptureRawPreview's source resolution but exposes metadata too.
 */
export function SourcePreviewDialog({
  item,
  onClose,
  onResolveFile,
}: {
  item: CaptureItem | null;
  onClose: () => void;
  onResolveFile: (endpoint: string) => Promise<string>;
}) {
  const [cachedUrl, setCachedUrl] = React.useState("");
  const [cacheSourceName, setCacheSourceName] = React.useState("");
  const [noteText, setNoteText] = React.useState("");
  const [resolvedUrl, setResolvedUrl] = React.useState("");
  const [previewError, setPreviewError] = React.useState("");
  const fileEndpoint = item?.fileEndpoint || (item?.sourceUrl?.startsWith("/api/v1/") && item.sourceUrl.endsWith("/file") ? item.sourceUrl : "");

  React.useEffect(() => {
    let revoked = false;
    setCachedUrl("");
    setCacheSourceName("");
    setNoteText("");
    setResolvedUrl("");
    setPreviewError("");
    if (!item) return;

    getCachedCapture(item.id)
      .then((cached) => {
        if (!cached || revoked) return;
        const url = URL.createObjectURL(cached.blob);
        setCachedUrl(url);
        setCacheSourceName(cached.sourceName);
        if (item.type === "note") void cached.blob.text().then((text) => !revoked && setNoteText(text));
      })
      .catch(() => undefined);

    return () => {
      revoked = true;
    };
  }, [item?.id, item?.type]);

  React.useEffect(() => {
    let cancelled = false;
    setResolvedUrl("");
    setPreviewError("");
    if (!item) return;
    if (!fileEndpoint) return;

    onResolveFile(fileEndpoint)
      .then((url) => {
        if (!cancelled) setResolvedUrl(url);
      })
      .catch(() => {
        if (!cancelled) setPreviewError("Source preview is not available right now.");
      });

    return () => {
      cancelled = true;
    };
  }, [fileEndpoint, item?.id, onResolveFile]);

  React.useEffect(() => {
    return () => {
      if (cachedUrl) URL.revokeObjectURL(cachedUrl);
    };
  }, [cachedUrl]);

  React.useEffect(() => {
    return () => {
      if (resolvedUrl.startsWith("blob:")) URL.revokeObjectURL(resolvedUrl);
    };
  }, [resolvedUrl]);

  if (!item) return null;

  const isAudio = item.type === "audio" || item.type === "voice";
  const directSourceUrl = item.sourceUrl?.startsWith("/api/v1/") ? "" : item.sourceUrl;
  const sourceUrl = cachedUrl || resolvedUrl || directSourceUrl || item.url;
  const sourceName = cacheSourceName || item.sourceName;
  const metadata = metadataRecord(item.metadata);
  const generated = generatedMetadataFor(item);
  const generatedText = metadataText(generated.text);
  const thumbnail = metadataDisplay(metadata.thumbnail || metadata.thumbnail_url || metadata.thumbnailUrl);

  return (
    <Dialog onClose={onClose} open title={item.title}>
      <div className="source-viewer">
        {item.type === "photo" ? (
          sourceUrl ? (
            <img alt={item.sourceName} className="photo-image-preview" src={sourceUrl} />
          ) : thumbnail ? (
            <img alt={`${item.sourceName} thumbnail`} className="photo-image-preview" src={thumbnail} />
          ) : (
            <div className="photo-frame">
              <span>{item.sourceName}</span>
            </div>
          )
        ) : null}
        {previewError ? <div className="alert alert-red">{previewError}</div> : null}
        {item.type === "note" ? (
          <Card className="source-note">
            <p>{generatedText || noteText || item.detail}</p>
          </Card>
        ) : null}
        {isAudio ? (
          <div className="audio-source">
            {sourceUrl ? (
              <audio controls src={sourceUrl} />
            ) : (
              <div className="audio-wave">
                <span />
                <span />
                <span />
                <span />
                <span />
                <span />
                <span />
              </div>
            )}
          </div>
        ) : null}
        <div className="source-info-panel">
          <div className="source-info-header">
            <small>{item.time} · File: {sourceName}</small>
            <StatusBadge status={item.status} />
          </div>
          <CaptureMetadataSummary item={item} />
        </div>
        {(item.type === "audio" || item.type === "photo") && generatedText ? (
          <Card className="source-note">
            <p>{generatedText}</p>
          </Card>
        ) : null}
      </div>
    </Dialog>
  );
}
