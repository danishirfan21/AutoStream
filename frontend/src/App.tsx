import { OverviewPage } from "./pages/OverviewPage";
import { VehicleDetailPage } from "./pages/VehicleDetailPage";
import { VehiclesPage } from "./pages/VehiclesPage";

export function App() {
  const path = window.location.pathname;
  const content = path === "/vehicles" ? <VehiclesPage /> : path.startsWith("/vehicles/") ? <VehicleDetailPage vin={decodeURIComponent(path.split("/").pop() ?? "")} /> : <OverviewPage />;
  return <main><nav><a href="/">AutoStream</a><a href="/">Overview</a><a href="/vehicles">Vehicles</a></nav>{content}</main>;
}
