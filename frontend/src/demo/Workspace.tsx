import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { WorkspaceContext } from './useWorkspace';
import { useAuth } from '../auth/useAuth';
import { createSession, seedWorkspace } from './model';
import type { Session, Task, Workspace } from './model';

const storageKey = 'inquispace-react-demo-v1';
const retiredDemoTaskIds = new Set(['qing-inquiry']);

function withoutRetiredDemoTasks(workspace: Workspace): Workspace {
  const tasks = Array.from(new Map(
    workspace.tasks
      .filter(task => !retiredDemoTaskIds.has(task.id))
      .map(task => [task.id, task]),
  ).values());
  const sessions = workspace.sessions.filter(session => !retiredDemoTaskIds.has(session.taskId));
  const selectedTaskId = tasks.some(task => task.id === workspace.selectedTaskId) ? workspace.selectedTaskId : (tasks[0]?.id ?? '');
  return { ...workspace, tasks, sessions, selectedTaskId };
}

function loadWorkspace(): Workspace {
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved) {
      const data = JSON.parse(saved) as Workspace;
      if (Array.isArray(data.tasks) && Array.isArray(data.sessions) && typeof data.studentId === 'string' && data.tasks.every(task => Array.isArray(task.publications) && Array.isArray(task.draft?.sources)) && data.sessions.every(session => Array.isArray(session.messages) && Array.isArray(session.corrections))) return withoutRetiredDemoTasks(data);
    }
  } catch { /* Unavailable browser storage must not prevent page previews. */ }
  return seedWorkspace();
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const [state, setState] = useState(loadWorkspace);
  const [storageError, setStorageError] = useState('');
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(state));
      setStorageError('');
    } catch {
      setStorageError('浏览器存储不可用或空间不足，当前修改仅保留在本次页面中。请勿刷新或关闭页面。');
    }
  }, [state]);
  useEffect(() => {
    if (session?.user.role !== 'student') return;
    setState(previous => previous.studentId === session.user.id ? previous : { ...previous, studentId: session.user.id });
  }, [session]);
  const updateTask = useCallback((id: string, change: (task: Task) => Task) => {
    setState(previous => ({ ...previous, tasks: previous.tasks.map(task => task.id === id ? change(task) : task) }));
  }, []);
  const updateSession = useCallback((id: string, change: (session: Session) => Session) => {
    setState(previous => ({ ...previous, sessions: previous.sessions.map(session => session.id === id ? change(session) : session) }));
  }, []);
  function openSession(task: Task) {
    const publication = task.publications.at(-1);
    const existing = state.sessions.find(session => session.taskId === task.id && session.studentId === state.studentId && session.publicationId === publication?.id);
    if (existing) return existing.id;
    const session = createSession(task, state.studentId);
    setState(previous => ({ ...previous, sessions: [...previous.sessions, session] }));
    return session.id;
  }
  return <WorkspaceContext.Provider value={{ state, setState, storageError, updateTask, updateSession, openSession }}>{children}</WorkspaceContext.Provider>;
}
