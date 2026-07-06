import React from "react";
import type { AftercareTemplate, AftercareTemplateDraft } from "../../domain/appTypes";
import { Button, Card } from "../../shared/ui/primitives";
import { useT } from "../../shared/i18n";

/**
 * AES-702 — manage per-procedure aftercare instruction templates. Deterministic templates, picked &
 * editable per send (AES-304) and attached to a curated share. Lives in Settings.
 */
export function AftercareTemplatesSettings({
  onList,
  onCreate,
  onUpdate,
  onDelete,
}: {
  onList: () => Promise<AftercareTemplate[]>;
  onCreate: (draft: AftercareTemplateDraft) => Promise<AftercareTemplate>;
  onUpdate: (id: string, draft: Partial<AftercareTemplateDraft>) => Promise<AftercareTemplate>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [templates, setTemplates] = React.useState<AftercareTemplate[]>([]);
  const [loaded, setLoaded] = React.useState(false);
  const [editing, setEditing] = React.useState<string | null>(null);
  const [adding, setAdding] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const t = useT();

  const reload = React.useCallback(() => {
    void onList()
      .then(setTemplates)
      .catch(() => undefined)
      .finally(() => setLoaded(true));
  }, [onList]);

  React.useEffect(() => {
    reload();
  }, [reload]);

  const create = async (draft: AftercareTemplateDraft) => {
    setBusy(true);
    try {
      await onCreate(draft);
      setAdding(false);
      reload();
    } finally {
      setBusy(false);
    }
  };

  const update = async (id: string, draft: Partial<AftercareTemplateDraft>) => {
    setBusy(true);
    try {
      await onUpdate(id, draft);
      setEditing(null);
      reload();
    } finally {
      setBusy(false);
    }
  };

  const remove = async (template: AftercareTemplate) => {
    if (!window.confirm(t("aftercare.confirmDelete", { name: template.name }))) return;
    setBusy(true);
    try {
      await onDelete(template.id);
      reload();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="settings-group settings-group--wide">
      <div className="settings-group-head">
        <h2>{t("aftercare.title")}</h2>
        <p>{t("aftercare.subtitle")}</p>
      </div>

      <div className="aftercare-list">
        {!loaded ? (
          <p className="aftercare-empty">{t("aftercare.loading")}</p>
        ) : templates.length ? (
          templates.map((template) =>
            editing === template.id ? (
              <AftercareEditor key={template.id} busy={busy} initial={template} onCancel={() => setEditing(null)} onSave={(draft) => update(template.id, draft)} />
            ) : (
              <div className="aftercare-row" key={template.id}>
                <div className="aftercare-copy">
                  <strong>{template.name}</strong>
                  {template.procedureType ? <span className="aftercare-procedure">{template.procedureType}</span> : null}
                  <p>{template.body}</p>
                </div>
                <div className="aftercare-actions">
                  <button className="aftercare-edit" disabled={busy} onClick={() => setEditing(template.id)} type="button">{t("aftercare.edit")}</button>
                  <button className="aftercare-delete" disabled={busy} onClick={() => void remove(template)} type="button">{t("aftercare.delete")}</button>
                </div>
              </div>
            ),
          )
        ) : (
          <p className="aftercare-empty">{t("aftercare.empty")}</p>
        )}
      </div>

      {adding ? (
        <AftercareEditor busy={busy} onCancel={() => setAdding(false)} onSave={create} />
      ) : (
        <div className="settings-group-actions">
          <Button onClick={() => setAdding(true)} size="sm" type="button">
            <span aria-hidden="true">+</span> {t("aftercare.add")}
          </Button>
        </div>
      )}
    </Card>
  );
}

function AftercareEditor({
  initial,
  busy,
  onSave,
  onCancel,
}: {
  initial?: AftercareTemplate;
  busy?: boolean;
  onSave: (draft: AftercareTemplateDraft) => void | Promise<void>;
  onCancel: () => void;
}) {
  const t = useT();
  const [name, setName] = React.useState(initial?.name || "");
  const [procedureType, setProcedureType] = React.useState(initial?.procedureType || "");
  const [body, setBody] = React.useState(initial?.body || "");
  const canSave = name.trim().length > 0 && body.trim().length > 0 && !busy;

  return (
    <div className="aftercare-editor">
      <label className="aftercare-field">
        <span>{t("aftercare.fieldName")}</span>
        <input onChange={(event) => setName(event.target.value)} placeholder={t("aftercare.namePlaceholder")} value={name} />
      </label>
      <label className="aftercare-field">
        <span>{t("aftercare.procedureType")} <small>{t("aftercare.optional")}</small></span>
        <input onChange={(event) => setProcedureType(event.target.value)} placeholder={t("aftercare.procedurePlaceholder")} value={procedureType} />
      </label>
      <label className="aftercare-field">
        <span>{t("aftercare.instructions")}</span>
        <textarea onChange={(event) => setBody(event.target.value)} placeholder={t("aftercare.instructionsPlaceholder")} rows={3} value={body} />
      </label>
      <div className="aftercare-editor-actions">
        <button className="aftercare-cancel" onClick={onCancel} type="button">{t("aftercare.cancel")}</button>
        <button
          className="aftercare-save"
          disabled={!canSave}
          onClick={() => void onSave({ name: name.trim(), procedureType: procedureType.trim() || null, body: body.trim() })}
          type="button"
        >
          {busy ? t("aftercare.saving") : t("aftercare.save")}
        </button>
      </div>
    </div>
  );
}
