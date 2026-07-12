import React from "react";
import type { ApiFetch } from "../../domain/appTypes";
import { Badge, Button, Input, Skeleton, Textarea } from "../../shared/ui/primitives";
import { useT } from "../../shared/i18n";
import {
  createQaTemplate,
  deleteQaTemplate,
  fetchQaLibrary,
  setQaExemplarStatus,
  updateQaTemplate,
  type LibraryItem,
  type QaLibraryResponse,
  type QaTemplateInput,
} from "./qaClient";

/**
 * Q&A knowledge library (AES-410) — the curation surface for the retrieval corpus that grounds reply
 * drafts. Two sections: hand-authored **templates** (add / edit / delete) and **indexed replies**
 * (previously-sent answers the doctor can exclude from — or re-include into — retrieval).
 *
 * Pro-only: the parent (`DoctorQaInbox`) is mounted for Pro tenants only, so this needs no extra gate.
 * All chrome is localized via `t()`; template/reply text (title, question pattern, answer, tags) is
 * verbatim clinical CONTENT and is rendered as-is.
 */
export function LibraryTab({ apiFetch, onToast }: { apiFetch: ApiFetch; onToast?: (message: string) => void }) {
  const t = useT();
  const [data, setData] = React.useState<QaLibraryResponse | null>(null);
  const [error, setError] = React.useState(false);
  const [refresh, setRefresh] = React.useState(0);
  const [creating, setCreating] = React.useState(false);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  const reload = React.useCallback(() => setRefresh((value) => value + 1), []);

  React.useEffect(() => {
    let cancelled = false;
    setError(false);
    fetchQaLibrary(apiFetch)
      .then((next) => !cancelled && setData(next))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [apiFetch, refresh]);

  const handleCreate = async (body: QaTemplateInput) => {
    setBusy(true);
    try {
      await createQaTemplate(apiFetch, body);
      onToast?.(t("qa.library.savedToast"));
      setCreating(false);
      reload();
    } catch {
      onToast?.(t("qa.library.saveError"));
    } finally {
      setBusy(false);
    }
  };

  const handleUpdate = async (id: string, body: QaTemplateInput) => {
    setBusy(true);
    try {
      await updateQaTemplate(apiFetch, id, body);
      onToast?.(t("qa.library.savedToast"));
      setEditingId(null);
      reload();
    } catch {
      onToast?.(t("qa.library.saveError"));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (item: LibraryItem) => {
    if (!window.confirm(t("qa.library.deleteConfirm"))) return;
    try {
      await deleteQaTemplate(apiFetch, item.id);
      onToast?.(t("qa.library.deletedToast"));
      reload();
    } catch {
      onToast?.(t("qa.library.saveError"));
    }
  };

  const handleStatus = async (item: LibraryItem, status: "active" | "excluded") => {
    try {
      await setQaExemplarStatus(apiFetch, item.id, status);
      onToast?.(status === "excluded" ? t("qa.library.excludedToast") : t("qa.library.includedToast"));
      reload();
    } catch {
      onToast?.(t("qa.library.saveError"));
    }
  };

  return (
    <div className="qa-library" data-testid="qa-library" role="tabpanel">
      {/* One quiet notice when hybrid semantic matching is off (AES-1802): retrieval is lexical-only,
          so a paraphrase may miss. Silent degradation is how this went unnoticed — so it's visible now. */}
      {data && !data.semanticSearch ? (
        <p className="qa-lib-notice" data-testid="qa-semantic-off">
          {t("qa.library.semanticOff")}
        </p>
      ) : null}
      {/* Templates ------------------------------------------------------------------------------ */}
      <section className="qa-lib-section">
        <div className="qa-lib-section-head">
          <h2>{t("qa.library.templates")}</h2>
          {data ? <span className="qa-lib-count">{t("qa.library.count", { templates: data.counts.templates })}</span> : null}
          {!creating ? (
            <Button
              className="qa-lib-new"
              size="sm"
              data-testid="qa-library-new"
              onClick={() => {
                setEditingId(null);
                setCreating(true);
              }}
            >
              {t("qa.library.newTemplate")}
            </Button>
          ) : null}
        </div>

        {creating ? (
          <TemplateForm busy={busy} onSubmit={handleCreate} onCancel={() => setCreating(false)} />
        ) : null}

        {error ? (
          <p className="qa-lib-empty">{t("qa.library.loadError")}</p>
        ) : data === null ? (
          <Skeleton className="h-16" />
        ) : data.templates.length === 0 && !creating ? (
          <p className="qa-lib-empty">{t("qa.library.empty")}</p>
        ) : (
          data.templates.map((item) =>
            editingId === item.id ? (
              <TemplateForm
                key={item.id}
                initial={item}
                busy={busy}
                onSubmit={(body) => handleUpdate(item.id, body)}
                onCancel={() => setEditingId(null)}
              />
            ) : (
              <TemplateRow
                key={item.id}
                item={item}
                onEdit={() => {
                  setCreating(false);
                  setEditingId(item.id);
                }}
                onDelete={() => handleDelete(item)}
              />
            ),
          )
        )}
      </section>

      {/* Indexed replies ------------------------------------------------------------------------ */}
      <section className="qa-lib-section">
        <div className="qa-lib-section-head">
          <h2>{t("qa.library.sentReplies")}</h2>
        </div>
        {!data ? (
          <Skeleton className="h-12" />
        ) : data.sentReplies.length === 0 ? (
          <p className="qa-lib-empty">{t("qa.library.emptyReplies")}</p>
        ) : (
          data.sentReplies.map((item) => (
            <SentReplyRow key={item.id} item={item} onStatus={(status) => handleStatus(item, status)} />
          ))
        )}
      </section>
    </div>
  );
}

/** One curated-template row: verbatim content + Edit / Delete actions. Exported for hermetic tests. */
export function TemplateRow({ item, onEdit, onDelete }: { item: LibraryItem; onEdit: () => void; onDelete: () => void }) {
  const t = useT();
  return (
    <div className="qa-lib-row" data-testid="qa-template-row">
      <div className="qa-lib-row-body">
        {/* Question is the primary line now (AES-1802); the optional title reads as a small label. */}
        {item.question ? (
          <span className="qa-lib-row-question" dir="auto" data-content>
            {item.question}
          </span>
        ) : null}
        {item.title ? (
          <span className="qa-lib-row-title" dir="auto" data-content>
            {item.title}
          </span>
        ) : null}
        <span className="qa-lib-row-answer" dir="auto" data-content>
          {item.answer}
        </span>
        {item.tags.length ? (
          <span className="qa-lib-tags" dir="auto" data-content>
            {item.tags.map((tag) => (
              <span className="qa-lib-tag" key={tag}>
                {tag}
              </span>
            ))}
          </span>
        ) : null}
      </div>
      <div className="qa-lib-row-actions">
        <button type="button" className="qa-lib-link" onClick={onEdit}>
          {t("qa.library.edit")}
        </button>
        <button type="button" className="qa-lib-link qa-lib-danger" onClick={onDelete}>
          {t("qa.library.delete")}
        </button>
      </div>
    </div>
  );
}

/** One indexed sent-reply row: verbatim answer + include/exclude control. */
function SentReplyRow({ item, onStatus }: { item: LibraryItem; onStatus: (status: "active" | "excluded") => void }) {
  const t = useT();
  const excluded = item.status === "excluded";
  return (
    <div className={`qa-lib-row qa-lib-reply${excluded ? " qa-lib-excluded" : ""}`}>
      <div className="qa-lib-row-body">
        {item.title ? (
          <span className="qa-lib-row-title" dir="auto" data-content>
            {item.title}
          </span>
        ) : null}
        <span className="qa-lib-row-answer" dir="auto" data-content>
          {item.answer}
        </span>
      </div>
      <div className="qa-lib-row-actions">
        {excluded ? (
          <>
            <Badge tone="neutral">{t("qa.library.excludedBadge")}</Badge>
            <button type="button" className="qa-lib-link" onClick={() => onStatus("active")}>
              {t("qa.library.include")}
            </button>
          </>
        ) : (
          <button type="button" className="qa-lib-link" onClick={() => onStatus("excluded")}>
            {t("qa.library.exclude")}
          </button>
        )}
      </div>
    </div>
  );
}

/** Inline add/edit form for a curated template. `answer` is required; the rest are optional. */
function TemplateForm({
  initial,
  busy,
  onSubmit,
  onCancel,
}: {
  initial?: LibraryItem;
  busy: boolean;
  onSubmit: (body: QaTemplateInput) => void;
  onCancel: () => void;
}) {
  const t = useT();
  const [question, setQuestion] = React.useState(initial?.question ?? "");
  const [title, setTitle] = React.useState(initial?.title ?? "");
  const [answer, setAnswer] = React.useState(initial?.answer ?? "");
  const [tags, setTags] = React.useState((initial?.tags ?? []).join(", "));
  const [questionError, setQuestionError] = React.useState(false);
  const [answerError, setAnswerError] = React.useState(false);

  const submit = () => {
    // Question is now the PRIMARY, required field (AES-1802): it's the retrieval signal, so steering it
    // here is the guard against the owner's trap (a question typed into the optional title, question empty).
    const missingQuestion = !question.trim();
    const missingAnswer = !answer.trim();
    setQuestionError(missingQuestion);
    setAnswerError(missingAnswer);
    if (missingQuestion || missingAnswer) return;
    onSubmit({
      title: title.trim() || null,
      question: question.trim(),
      answer: answer.trim(),
      tags: tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    });
  };

  return (
    <div className="qa-lib-form">
      {/* Question is the primary field (AES-1802): a labelled textarea, not a small input, so it never
          reads as just a label. Title sits below as an optional small input. */}
      <label className="qa-lib-field-label" htmlFor="qa-tpl-question">
        {t("qa.library.questionPrimary")}
        <span className="qa-lib-req" aria-hidden="true"> *</span>
      </label>
      <Textarea
        id="qa-tpl-question"
        className="qa-lib-question"
        rows={2}
        dir="auto"
        data-testid="qa-template-question"
        placeholder={t("qa.library.questionExample")}
        aria-label={t("qa.library.questionPrimary")}
        value={question}
        onChange={(event) => {
          setQuestion(event.target.value);
          if (questionError) setQuestionError(false);
        }}
      />
      {questionError ? <div className="qa-lib-error">{t("qa.library.questionRequired")}</div> : null}
      <Input
        className="qa-lib-input"
        dir="auto"
        data-testid="qa-template-title"
        placeholder={t("qa.library.titleOptional")}
        aria-label={t("qa.library.titleOptional")}
        value={title}
        onChange={(event) => setTitle(event.target.value)}
      />
      <Textarea
        className="qa-lib-answer"
        dir="auto"
        data-testid="qa-template-answer"
        placeholder={t("qa.library.answer")}
        aria-label={t("qa.library.answer")}
        value={answer}
        onChange={(event) => {
          setAnswer(event.target.value);
          if (answerError) setAnswerError(false);
        }}
      />
      {answerError ? <div className="qa-lib-error">{t("qa.library.answerRequired")}</div> : null}
      <Input
        className="qa-lib-input"
        dir="auto"
        placeholder={t("qa.library.tags")}
        aria-label={t("qa.library.tags")}
        value={tags}
        onChange={(event) => setTags(event.target.value)}
      />
      <span className="qa-lib-hint">{t("qa.library.tagsHint")}</span>
      <div className="qa-lib-form-actions">
        <Button size="sm" data-testid="qa-template-save" onClick={submit} disabled={busy}>
          {t("qa.library.save")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
          {t("qa.library.cancel")}
        </Button>
      </div>
    </div>
  );
}
