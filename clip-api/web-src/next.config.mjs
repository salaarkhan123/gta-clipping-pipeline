/** Static export: the site is plain files served by Caddy. No Node process runs on the server. */
export default { output: "export", trailingSlash: true, images: { unoptimized: true } };
