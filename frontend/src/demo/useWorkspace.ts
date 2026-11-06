import { createContext, useContext } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { Session, Task, Workspace } from './model';

interface WorkspaceContext {
  state: Workspace;
  setState: Dispatch<SetStateAction<Workspace>>;
  storageError: string;
  updateTask: (id: string, change: (task: Task) => Task) => void;
  updateSession: (id: string, change: (session: Session) => Session) => void;
  openSession: (task: Task) => string;
}
export const WorkspaceContext = createContext<WorkspaceContext | null>(null);

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error('页面缺少工作区。');
  return context;
}
