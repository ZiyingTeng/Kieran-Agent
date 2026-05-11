/**
 * TopBar Component
 */

import { UserControl } from './UserControl';
import { ModelPanel } from './ModelPanel';

export function TopBar() {
  return (
    <div className="bg-gradient-to-r from-[#ff6b9d] via-[#ff85a1] to-[#c44569] text-white px-6 py-4 flex items-center justify-between shadow-lg">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
          <span className="text-xl">💕</span>
        </div>
        <h1 className="text-xl font-bold tracking-wide">AI女友聊天系统</h1>
      </div>
      <div className="flex items-center gap-4">
        <ModelPanel />
        <UserControl />
      </div>
    </div>
  );
}
