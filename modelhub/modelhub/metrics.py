"""
Copyright 2021 Objectiv B.V.
"""
import pandas as pd

# todo these methods can be rewritten as bach's quite easily

class Metrics:
    @staticmethod
    def get_confusion_matrix(y, y_pred):
        df = pd.DataFrame({'y': y})
        df['y_pred'] = y_pred
        confusion_matrix = df.value_counts().unstack()
        return confusion_matrix

    @classmethod
    def _precision_recall(cls, y, y_pred, return_class_true=True, return_precision=True):
        """
        :param return_class_true: get precision for the 'True' class.
        """
        confusion_matrix = cls.get_confusion_matrix(y, y_pred)
        precision = confusion_matrix / confusion_matrix.sum()
        recall = confusion_matrix / confusion_matrix.sum(axis=1)

        return_data = recall
        if return_precision:
            return_data = precision

        if return_class_true == True:
            return return_data.loc[1, 1]
        return return_data.loc[0, 0]

    @classmethod
    def get_precision(cls, y, y_pred, return_class_true=True):
        return cls._precision_recall(y, y_pred, return_class_true=return_class_true, return_precision=True)

    @classmethod
    def get_recall(cls, y, y_pred, return_class_true=True):
        return cls._precision_recall(y, y_pred, return_class_true=return_class_true, return_precision=False)

    @staticmethod
    def get_f1_score(precision, recall):
        return 2 * (precision * recall) / (precision + recall)

    @classmethod
    def get_classification_report(cls, y, y_pred, output_dict=False):
        report = '              precision    recall  f1-score\n\n'
        report_dict = {}
        for return_class_true in [False, True]:
            precision = cls.get_precision(y, y_pred, return_class_true=return_class_true)

            recall = cls.get_recall(y, y_pred, return_class_true=return_class_true)
            f1 = cls.get_f1_score(precision, recall)
            report_dict[return_class_true] = {'precision': precision, 'recall': recall, 'f1': f1}
            report += f"{return_class_true}: {precision}  {recall}  {f1} \n"

        macro_avg_f1 = (report_dict[False]['f1'] + report_dict[True]['f1']) / 2
        report_dict['macro_avg'] = {'f1': macro_avg_f1}
        report += f"\nmacro avg:                           {macro_avg_f1} \n"

        weighted_avg_f1 = (report_dict[False]['f1'] * len(y[y == 0]) + report_dict[True]['f1'] * len(
            y[y == 1])) / len(y)
        report_dict['weighted_avg'] = {'f1': weighted_avg_f1}
        report += f"weighted avg:                           {weighted_avg_f1} \n"

        if output_dict:
            return report_dict
        return report

