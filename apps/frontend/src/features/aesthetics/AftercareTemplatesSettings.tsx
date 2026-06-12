import React from "react";
import type { AftercareTemplate, AftercareTemplateDraft } from "../../domain/appTypes";
import { Button, Card } from "../../shared/ui/primitives";

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
    if (!window.confirm(`Delete the "${template.name}" aftercare template?`)) return;
    setBusy(true);
    try {
      await onDelete(template.id);
      reload();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="settings-group">
      <div className="settings-group-head">
        <h2>Aftercare templates</h2>
        <p>Per-procedure instructions the patient sees on a shared report. Pick and edit one per send.</p>
      </div>

      <div className="aftercare-list">
        {!loaded ? (
          <p className="aftercare-empty">Loading templates…</p>
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
                  <button className="aftercare-edit" disabled={busy} onClick={() => setEditing(template.id)} type="button">Edit</button>
                  <button className="aftercare-delete" disabled={busy} onClick={() => void remove(template)} type="button">Delete</button>
                </div>
              </div>
            ),
          )
        ) : (
          <p className="aftercare-empty">No aftercare templates yet. Add one so it can be attached to a shared report.</p>
        )}
      </div>

      {adding ? (
        <AftercareEditor busy={busy} onCancel={() => setAdding(false)} onSave={create} />
      ) : (
        <div className="settings-group-actions">
          <Button onClick={() => setAdding(true)} size="sm" type="button">
            <span aria-hidden="true">+</span> Add template
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
  const [name, setName] = React.useState(initial?.name || "");
  const [procedureType, setProcedureType] = React.useState(initial?.procedureType || "");
  const [body, setBody] = React.useState(initial?.body || "");
  const canSave = name.trim().length > 0 && body.trim().length > 0 && !busy;

  return (
    <div className="aftercare-editor">
      <label className="aftercare-field">
        <span>Name</span>
        <input onChange={(event) => setName(event.target.value)} placeholder="Botox aftercare" value={name} />
      </label>
      <label className="aftercare-field">
        <span>Procedure type <small>· optional</small></span>
        <input onChange={(event) => setProcedureType(event.target.value)} placeholder="botox" value={procedureType} />
      </label>
      <label className="aftercare-field">
        <span>Instructions</span>
        <textarea onChange={(event) => setBody(event.target.value)} placeholder="Avoid lying down for 4 hours." rows={3} value={body} />
      </label>
      <div className="aftercare-editor-actions">
        <button className="aftercare-cancel" onClick={onCancel} type="button">Cancel</button>
        <button
          className="aftercare-save"
          disabled={!canSave}
          onClick={() => void onSave({ name: name.trim(), procedureType: procedureType.trim() || null, body: body.trim() })}
          type="button"
        >
          {busy ? "Saving…" : "Save template"}
        </button>
      </div>
    </div>
  );
}
