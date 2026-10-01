import {
  createContext,
  useContext,
  useEffect,
  useState,
  type PropsWithChildren,
} from "react";
import { FrontierPage, type FrontierPageProps } from "./FrontierPage";
import type { FrontierDataset } from "./dataset";
import { readFrontierDataset } from "./frontierApi";
const PreviewContext = createContext<FrontierDataset | null>(null);

// Explicit, isolated snapshot injection for review sites/tests. Production never
// silently falls back to seed data when the persistent service fails.
export function FrontierPreviewProvider({
  data,
  children,
}: PropsWithChildren<{ data: FrontierDataset }>) {
  return (
    <PreviewContext.Provider value={data}>{children}</PreviewContext.Provider>
  );
}
export function FrontierConnectedPage(props: Omit<FrontierPageProps, "data">) {
  const preview = useContext(PreviewContext);
  const [data, setData] = useState<FrontierDataset | null>(preview);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (preview) {
      setData(preview);
      return;
    }
    let cancelled = false;
    setError("");
    void readFrontierDataset()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((reason: unknown) => {
        if (!cancelled)
          setError(
            reason instanceof Error ? reason.message : "学术前沿暂时无法读取",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [preview, retry]);
  if (!data)
    return (
      <section className="knowledge-surface frontier">
        <div className="frontier-empty" role={error ? "alert" : "status"}>
          <h1>学术前沿</h1>
          <p>{error || "正在读取前沿资料…"}</p>
          {error ? (
            <button
              type="button"
              onClick={() => setRetry((current) => current + 1)}
            >
              重新加载
            </button>
          ) : null}
          <button type="button" onClick={props.onOpenLibrary}>
            返回知识库
          </button>
        </div>
      </section>
    );
  return <FrontierPage {...props} data={data} />;
}
