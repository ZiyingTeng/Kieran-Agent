/**
 * ModelPanel Component - Dropdown for model settings
 */

import { useEffect, useState, useRef } from 'react';
import { useModelStore } from '@/stores/modelStore';
import * as api from '@/api';
import { clsx } from 'clsx';

export function ModelPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const {
    availableModels,
    currentModel,
    customApiPath,
    useAigirlApi,
    setAvailableModels,
    setCurrentModel,
    setCustomApiPath,
    setUseAigirlApi,
  } = useModelStore();

  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    type: 'success' | 'error' | 'info';
    message: string;
  } | null>(null);

  useEffect(() => {
    const loadModels = async () => {
      try {
        const response = await api.getModels();
        if (response.success && response.models) {
          setAvailableModels(response.models);
        }
      } catch (error) {
        console.error('Failed to load models:', error);
      }
    };

    loadModels();
  }, [setAvailableModels]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const getCurrentModelDisplay = () => {
    if (!currentModel) return '默认模型';
    const model = availableModels.find((m) => m.id === currentModel);
    if (!model) return '默认模型';
    const desc = model.description;
    return desc.length > 15 ? desc.substring(0, 15) + '...' : desc;
  };

  const handleTest = async () => {
    setIsTesting(true);
    setTestResult({ type: 'info', message: '测试中...' });

    try {
      const response = await api.testApiConnection({
        userId: 'user_001',
        expertId: '101',
        mes: '你好，这是一条测试消息',
        source: '0',
        modelName: currentModel,
        apiPath: customApiPath,
      });

      if (response.success && response.content) {
        setTestResult({
          type: 'success',
          message: `✅ 连接成功！回复: ${response.content.substring(0, 50)}...`,
        });
      } else {
        setTestResult({
          type: 'error',
          message: `❌ 测试失败: ${response.error || '未知错误'}`,
        });
      }
    } catch (error) {
      setTestResult({
        type: 'error',
        message: `❌ 连接失败: ${(error as Error).message}`,
      });
    } finally {
      setIsTesting(false);
    }
  };

  const selectedModel = availableModels.find((m) => m.id === currentModel);

  return (
    <div className="relative" ref={panelRef}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="px-4 py-2.5 bg-white/20 backdrop-blur-sm border-2 border-white/30 rounded-full text-white text-sm hover:bg-white/30 transition-all flex items-center gap-2 shadow-lg hover:shadow-xl"
      >
        <span className="flex items-center gap-1.5">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          <span className="max-w-[150px] truncate font-medium">{getCurrentModelDisplay()}</span>
        </span>
        <svg className={`w-3 h-3 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Panel */}
      {isOpen && (
        <div className="absolute top-full right-0 mt-2 w-[320px] bg-white rounded-xl shadow-xl p-5 z-50 animate-fade-in">
          <h3 className="text-base font-semibold text-gray-900 mb-4">模型设置</h3>

          {/* Model Selection */}
          <div className="mb-4">
            <label className="block text-sm text-gray-600 mb-2">
              选择模型
            </label>
            <div className="relative">
              <select
                value={currentModel}
                onChange={(e) => setCurrentModel(e.target.value)}
                className="w-full px-3 py-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary text-sm text-gray-800 appearance-none cursor-pointer hover:bg-gray-100 transition-colors"
              >
                <option value="">使用默认模型</option>
                {availableModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.description} {model.is_default ? '(默认)' : ''}
                  </option>
                ))}
              </select>
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none">
                ▼
              </span>
            </div>
            {selectedModel && (
              <p className="text-xs text-gray-500 mt-1.5">
                {selectedModel.description}
              </p>
            )}
          </div>

          {/* Custom API Path (for models without API key) */}
          {selectedModel && !selectedModel.requires_api_key && (
            <div className="mb-4">
              <label className="block text-sm text-gray-600 mb-2">
                自定义API路径
              </label>
              <input
                type="text"
                value={customApiPath}
                onChange={(e) => setCustomApiPath(e.target.value)}
                placeholder="例如: http://localhost:11434/v1"
                className="w-full px-3 py-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary text-sm text-gray-800 placeholder-gray-400 hover:bg-gray-100 transition-colors"
              />
            </div>
          )}

          {/* AIGirl API Toggle */}
          <div className="pt-4 border-t border-gray-100 flex items-center justify-between">
            <label className="text-sm text-gray-600">
              启用AIGirl兼容API
            </label>
            <button
              onClick={() => setUseAigirlApi(!useAigirlApi)}
              className={clsx(
                'w-12 h-6 rounded-full transition-colors duration-200 relative shadow-sm',
                useAigirlApi ? 'bg-gradient-to-r from-pink-500 to-rose-500' : 'bg-gray-300'
              )}
            >
              <span
                className={clsx(
                  'absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-md transition-transform duration-200',
                  useAigirlApi && 'translate-x-6'
                )}
              />
            </button>
          </div>

          {/* Test Button */}
          <button
            onClick={handleTest}
            disabled={isTesting}
            className="w-full mt-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors disabled:opacity-50"
          >
            {isTesting ? '测试中...' : '测试连接'}
          </button>

          {/* Test Result */}
          {testResult && (
            <p
              className={clsx(
                'text-xs mt-2',
                testResult.type === 'success' && 'text-green-600',
                testResult.type === 'error' && 'text-red-600',
                testResult.type === 'info' && 'text-gray-500'
              )}
            >
              {testResult.message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
