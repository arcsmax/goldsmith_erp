// Materials Page Component
import React, { useEffect, useState } from 'react';
import { materialsApi } from '../api';
import { MaterialType } from '../types';
import '../styles/pages.css';

export const MaterialsPage: React.FC = () => {
  const [materials, setMaterials] = useState<MaterialType[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMaterials();
  }, []);

  const fetchMaterials = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await materialsApi.getAll();
      setMaterials(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Fehler beim Laden der Materialien');
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return <div className="page-loading">Lade Materialien...</div>;
  }

  if (error) {
    return <div className="page-error">{error}</div>;
  }

  return (
    <div className="page-container">
      <header className="page-header">
        <h1>Materialien</h1>
        <button className="btn-primary">+ Neues Material</button>
      </header>

      {materials.length === 0 ? (
        <div className="empty-state">
          <p>Keine Materialien vorhanden.</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Beschreibung</th>
                <th>Preis/Einheit</th>
                <th>Bestand</th>
                <th>Einheit</th>
                <th>Wert</th>
              </tr>
            </thead>
            <tbody>
              {materials.map((material) => (
                <tr key={material.id}>
                  <td>#{material.id}</td>
                  <td>{material.name}</td>
                  <td>{material.description || '-'}</td>
                  <td>{material.unit_price.toFixed(2)} €</td>
                  <td className={material.stock < 10 ? 'low-stock' : ''}>
                    {material.stock}
                  </td>
                  <td>{material.unit}</td>
                  <td>{(material.unit_price * material.stock).toFixed(2)} €</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
