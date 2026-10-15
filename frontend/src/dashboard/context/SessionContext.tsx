import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { z } from "zod";
import { DashboardError, request, safeError } from "../api/client";
import { invalidateSecurity, subscribeSecurity } from "../api/security";
import { authEnvelope, userSchema, type User } from "../schemas/business";

const SessionContext = createContext<{ user: User; logout: () => void } | null>(null);
export function useSession() {
  return useContext(SessionContext);
}

export function SessionGate({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [epoch, setEpoch] = useState(0);
  const current = useRef(0);
  const active = useRef<AbortController | null>(null);
  const reset = useCallback(() => {
    current.current++;
    active.current?.abort();
    active.current = null;
    setUser(null);
    setBusy(false);
    setLoading(false);
    setEpoch((v) => v + 1);
  }, []);
  useEffect(
    () =>
      subscribeSecurity((kind) => {
        if (kind === "session") {
          reset();
          setMessage("登录已失效，请重新登录。");
        }
      }),
    [reset],
  );
  useEffect(() => {
    const controller = new AbortController();
    const generation = ++current.current;
    active.current = controller;
    void request("/api/v1/auth/me", authEnvelope(userSchema), controller.signal)
      .then((result) => {
        if (!controller.signal.aborted && current.current === generation) setUser(result.data);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && current.current === generation)
          setMessage(safeError(error));
      })
      .finally(() => {
        if (!controller.signal.aborted && current.current === generation) setLoading(false);
      });
    return () => {
      controller.abort();
      active.current?.abort();
      current.current++;
    };
  }, []);
  // Recheck on return to the tab, and while it remains open. HTTP still checks
  // every request; this poll removes idle sensitive state after remote revocation.
  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    const check = () => {
      void request("/api/v1/auth/me", authEnvelope(userSchema), controller.signal)
        .then(({ data }) => {
          if (controller.signal.aborted) return;
          if (
            data.principal_id !== user.principal_id ||
            data.auth_revision !== user.auth_revision ||
            data.grant_revision !== user.grant_revision
          ) {
            invalidateSecurity("session");
          }
        })
        .catch(() => {
          /* Errors are safely handled by the shared request boundary. */
        });
    };
    window.addEventListener("focus", check);
    const timer = window.setInterval(check, 60000);
    return () => {
      controller.abort();
      window.removeEventListener("focus", check);
      window.clearInterval(timer);
    };
  }, [user]);
  async function submit(form: HTMLFormElement) {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    const generation = ++current.current;
    const fields = Object.fromEntries(new FormData(form));
    const changing = !!user?.must_change_password;
    setBusy(true);
    setMessage("");
    try {
      await request(
        changing ? "/api/v1/auth/change-password" : "/api/v1/auth/login",
        authEnvelope(
          z.object(
            changing
              ? { password_changed: z.literal(true) }
              : {
                  principal_id: z.string(),
                  role: z.enum(["ADMIN", "BUSINESS_USER"]),
                  must_change_password: z.boolean(),
                },
          ),
        ),
        controller.signal,
        undefined,
        fields,
      );
      const result = await request("/api/v1/auth/me", authEnvelope(userSchema), controller.signal);
      if (!controller.signal.aborted && generation === current.current) {
        setUser(result.data);
        setEpoch((v) => v + 1);
        form.reset();
      }
    } catch (error) {
      if (!controller.signal.aborted && generation === current.current)
        setMessage(
          error instanceof DashboardError && error.status === 401
            ? "用户名或密码不正确，或账号不可用。"
            : safeError(error),
        );
    } finally {
      if (!controller.signal.aborted && generation === current.current) setBusy(false);
    }
  }
  async function logout() {
    // Unmount every business component before waiting for the network.
    invalidateSecurity("access");
    setUser(null);
    setLoading(true);
    let failed = false;
    try {
      await request(
        "/api/v1/auth/logout",
        authEnvelope(z.object({ logged_out: z.literal(true) })),
        new AbortController().signal,
        undefined,
        {},
      );
    } catch {
      failed = true;
    } finally {
      invalidateSecurity("session");
      if (failed)
        setMessage(
          "本页业务数据已清除，但服务器尚未确认退出。请恢复连接后重试，不要将设备交给他人。",
        );
    }
  }
  if (loading)
    return (
      <main className="dashboard d-auth" role="status">
        正在检查登录状态…
      </main>
    );
  if (!user || user.must_change_password)
    return (
      <main className="dashboard d-auth">
        <section className="d-panel">
          <h1>{user ? "首次登录 · 修改密码" : "登录蓝莓预测工作台"}</h1>
          <p>
            {user
              ? "请更换管理员提供的临时密码后再访问业务数据。"
              : "使用管理员创建的账号。不开放自行注册。"}
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void submit(event.currentTarget);
            }}
          >
            {!user && (
              <label>
                用户名
                <input
                  name="username"
                  required
                  minLength={3}
                  maxLength={64}
                  autoComplete="username"
                />
              </label>
            )}
            <label>
              {user ? "当前密码" : "密码"}
              <input
                name={user ? "current_password" : "password"}
                type="password"
                required
                maxLength={128}
                autoComplete="current-password"
              />
            </label>
            {user && (
              <label>
                新密码
                <input
                  name="new_password"
                  type="password"
                  required
                  minLength={15}
                  maxLength={128}
                  autoComplete="new-password"
                />
              </label>
            )}
            {message && <p role="alert">{message}</p>}
            <button className="d-primary" disabled={busy}>
              {busy ? "正在提交…" : user ? "修改密码并继续" : "登录"}
            </button>
          </form>
          {user && <button onClick={() => void logout()}>退出登录</button>}
        </section>
      </main>
    );
  return (
    <SessionContext.Provider value={{ user, logout: () => void logout() }}>
      <div key={epoch}>{children}</div>
    </SessionContext.Provider>
  );
}
