const SUPABASE_URL = "https://hblecztskfvltuerwmmr.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhibGVjenRza2Z2bHR1ZXJ3bW1yIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODAyNjk5MDQsImV4cCI6MjA5NTg0NTkwNH0.s1aULx9Shcd4awS1EeiG5R5KiQQWZNHAAqj3Isfg0YM";

const { createClient } = supabase;
const client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);


async function main() {
  console.log("Testing Supabase connection...");
  const { data, error } = await client.from("opinions").select("*");
  console.log("Supabase test:", data, error);

  loadOpinions();
}

document.getElementById("opinionForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const q1 = document.getElementById("q1").value;
  const q2 = document.getElementById("q2").value;
  const q3 = document.getElementById("q3").value;

  const { data, error } = await client
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
  const { data: opinions, error } = await client
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
        <p><strong>What I've Learned:</strong> ${op.q1}</p>
        <p><strong>What I'll Take Away:</strong> ${op.q2}</p>
        <p><strong>How I'll Counter Misconceptions:</strong> ${op.q3}</p>
        <span>${new Date(op.created_at).toLocaleString()}</span>
      </div>
    `)
    .join("");
}

main();
