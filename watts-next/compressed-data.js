// The public Pages copy keeps the larger release files compressed in Git.
async function wattsReleaseData(path) {
  const response = await fetch(path + ".gz");
  if (!response.ok || !response.body) return response;
  return new Response(response.body.pipeThrough(new DecompressionStream("gzip")), {
    headers: {"Content-Type": "application/json"}
  });
}
