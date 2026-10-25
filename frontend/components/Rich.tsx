/** Tiny formatter for explanation strings: **bold** and `code`. */
export default function Rich({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("**") ? <b key={i}>{p.slice(2, -2)}</b>
          : p.startsWith("`") ? <code key={i}>{p.slice(1, -1)}</code>
            : <span key={i}>{p}</span>,
      )}
    </>
  );
}
