import { redirect } from "next/navigation";

// Temporal: la landing pública llega en la fase F5; mientras tanto / lleva al chat
// (y el proxy redirige a /login si no hay sesión).
export default function Home() {
  redirect("/chat");
}
