import { useHashRoute } from '../hooks/useHashRoute';
import { Home } from './Home';
import { LabShell } from './LabShell';

/** Home at every hash that is not a Lab link; the Lab at `#/lab…`. */
export function App() {
  const { route } = useHashRoute();
  return route.kind === 'home' ? <Home /> : <LabShell />;
}
