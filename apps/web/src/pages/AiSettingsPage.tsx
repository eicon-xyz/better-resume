/** M5-T7: the AI settings panel — see and switch which provider serves each scene. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { SceneView } from "../api/types";
import { useApi } from "../api/useApi";
import { describeApiError, toApiError } from "../api/errors";
import { Button, Card } from "../components";
import { sceneKeys } from "../scenes/queries";
import styles from "./AiSettingsPage.module.css";

const ADAPTERS = ["openai_compat", "xingyun", "dashscope_app"] as const;

type AdapterKind = (typeof ADAPTERS)[number];

//: Which variable an operator has to set when a binding cannot run (mirrors the factories).
const CREDENTIAL_HINTS: Record<AdapterKind, string> = {
  openai_compat: "：BR_DEEPSEEK_API_KEY",
  xingyun: "：XINGCHEN_API_KEY / XINGCHEN_API_SECRET",
  dashscope_app: "：BR_DASHSCOPE_API_KEY（场景绑定里目标填应用 app_id）",
};

interface DraftState {
  adapter: AdapterKind;
  targetRef: string;
}

export function AiSettingsPage() {
  const api = useApi();
  const queryClient = useQueryClient();
  const [drafts, setDrafts] = useState<Record<string, DraftState>>({});
  const [error, setError] = useState<string | null>(null);

  const scenesQuery = useQuery({
    queryKey: sceneKeys.list(),
    queryFn: () => api.listScenes(),
  });

  const saveMutation = useMutation({
    mutationFn: (input: { scene: string; adapter: AdapterKind; targetRef: string }) =>
      api.updateScene(input.scene, { adapter: input.adapter, target_ref: input.targetRef }),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: sceneKeys.list() });
    },
    onError: (caught) => setError(describeApiError(toApiError(caught))),
  });

  if (scenesQuery.isLoading) return <p className={styles.loading}>正在读取场景绑定…</p>;
  if (scenesQuery.isError) {
    return (
      <p className={styles.error} role="alert">
        {describeApiError(toApiError(scenesQuery.error))}
      </p>
    );
  }

  const scenes: SceneView[] = scenesQuery.data ?? [];

  function draftFor(scene: SceneView): DraftState {
    return (
      drafts[scene.scene] ?? {
        adapter: (scene.adapter as AdapterKind) ?? "openai_compat",
        targetRef: scene.target_ref,
      }
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.brand}>AI 设置</h1>
        <Link to="/chat">返回对话</Link>
      </header>

      <Card title="场景绑定">
        <p className={styles.hint}>
          每个业务场景可以独立绑定供应商。<strong>切换供应商不需要改业务代码</strong>，下一次 AI
          调用即生效；密钥只从环境变量读取，这里只显示是否已配置。
        </p>
        {error ? (
          <p className={styles.error} role="alert">
            {error}
          </p>
        ) : null}
        <table className={styles.table}>
          <thead>
            <tr>
              <th>场景</th>
              <th>供应商</th>
              <th>目标（模型 / flow_id）</th>
              <th>状态</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {scenes.map((scene) => {
              const draft = draftFor(scene);
              const dirty = draft.adapter !== scene.adapter || draft.targetRef !== scene.target_ref;
              return (
                <tr key={scene.scene}>
                  <td>
                    <span className={styles.label}>{scene.label}</span>
                    <code className={styles.sceneName}>{scene.scene}</code>
                  </td>
                  <td>
                    <select
                      aria-label={`${scene.label} 供应商`}
                      value={draft.adapter}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [scene.scene]: { ...draft, adapter: event.target.value as AdapterKind },
                        }))
                      }
                    >
                      {ADAPTERS.map((adapter) => (
                        <option key={adapter} value={adapter}>
                          {adapter}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      aria-label={`${scene.label} 目标`}
                      value={draft.targetRef}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [scene.scene]: { ...draft, targetRef: event.target.value },
                        }))
                      }
                    />
                  </td>
                  <td>
                    {scene.configured ? (
                      <span className={styles.ok}>已配置</span>
                    ) : (
                      <span className={styles.missing}>
                        未配置（检查环境变量）
                        {CREDENTIAL_HINTS[scene.adapter as AdapterKind] ?? "：BR_DEEPSEEK_API_KEY"}
                      </span>
                    )}
                  </td>
                  <td>
                    <Button
                      size="sm"
                      disabled={!dirty}
                      loading={saveMutation.isPending && saveMutation.variables?.scene === scene.scene}
                      onClick={() =>
                        saveMutation.mutate({
                          scene: scene.scene,
                          adapter: draft.adapter,
                          targetRef: draft.targetRef,
                        })
                      }
                    >
                      保存
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
