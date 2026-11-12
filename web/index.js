document.getElementById("create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = document.getElementById("create-status");
  status.textContent = "모임을 만드는 중…";
  try {
    const res = await fetch("/api/rooms", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: document.getElementById("title").value }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || "모임을 만들지 못했어요.");
    location.href = `/r/${encodeURIComponent(data.id)}`;
  } catch (err) {
    status.textContent = err.message;
  }
});
