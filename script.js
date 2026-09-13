const supabase = supabase.createClient(
  SUPABASE_URL,
  SUPABASE_ANON_KEY
);

console.log("Testing Supabase connection...");
const { data, error } = await supabase.from("opinions").select("*");
console.log("Supabase test:", data, error);

document.getElementById("opinionForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const q1 = document.getElementById("q1").value;
  const q2 = document.getElementById("q2").value;
  const q3 = document.getElementById("q3").value;

  const { data, error } = await supabase
    .from("opinions")
    .insert([{ q1, q2, q3 }]);

  if (error) {
    console.error(error);
    return;
  }

  document.getElementById("q1").value = "";
  document.getElementById("q2").value = "";
  document.getElementById("q3").value = "";

  loadOpinions();
});

async function loadOpinions() {
  const { data: opinions, error } = await supabase
    .from("opinions")
    .select("*")
    .order("created_at", { ascending: false });

  if (error) {
    console.error(error);
    return;
  }

  const container = document.getElementById("opinionsList");

  container.innerHTML = opinions
    .map(op => `
      <div class="opinion-card">
        <h3>User Submission</h3>
        <p><strong>Misconception:</strong> ${op.q1}</p>
        <p><strong>Daily Life:</strong> ${op.q2}</p>
        <p><strong>Understanding:</strong> ${op.q3}</p>
        <span>${new Date(op.created_at).toLocaleString()}</span>
      </div>
    `)
    .join("");
}
